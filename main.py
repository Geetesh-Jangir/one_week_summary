"""
Main entry point: weekly prices, allowlisted RSS, scrape, causal scoring, and investor summary.
"""

import argparse
import json
import logging
import io
import contextlib
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from fund_data import (
    MIN_HOLDING_PCT,
    available_fund_ids,
    load_fund_bundle,
    resolve_fund_data_dir,
)
from demo import get_fund_weekly_prices
from stocks_for_news import (
    CAUSAL_SCORE_MIN,
    article_matches_move_sentiment,
    build_sector_moves,
    filter_articles_by_keyword,
    group_by_event,
    headline_holdings as select_headline_holdings,
    select_drags,
    select_final_events,
    select_news_targets,
    select_offsets,
)
from app import fetch_news_for_week, publisher_host_allowlisted
from news_relevancy_agent import (
    build_summary_facts,
    score_articles_causal,
    write_investor_summary,
)
from lib.fetch import thread_session
from web_scrapper import scrape_one, _write_record

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent
OUTPUT_SCRAPPER_DIR = ROOT / "output-scrapper"
OUT_DIR = ROOT / "out"
SCRAPE_WORKERS = 8


def clear_run_output_dirs() -> None:
    """Wipe scrape dumps and previous result.json so this run writes only fresh files."""
    for path in (OUT_DIR, OUTPUT_SCRAPPER_DIR):
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True, exist_ok=True)
    logger.info("Cleared %s and %s", OUT_DIR.name, OUTPUT_SCRAPPER_DIR.name)


def sort_by_weekly_nav_impact(holdings: list[dict]) -> list[dict]:
    """Negatives first (most negative), then positives (highest first)."""
    negative = [h for h in holdings if h.get("weekly_nav_impact_pct", 0) < 0]
    positive = [h for h in holdings if h.get("weekly_nav_impact_pct", 0) >= 0]
    negative.sort(key=lambda x: x.get("weekly_nav_impact_pct", 0))
    positive.sort(key=lambda x: x.get("weekly_nav_impact_pct", 0), reverse=True)
    return negative + positive


def _compact_price_only(holding: dict) -> dict:
    return {
        "name": holding.get("name"),
        "industry": holding.get("industry"),
        "ticker": holding.get("ticker"),
        "nav_percentage": holding.get("nav_percentage"),
        "weekly_change_pct": holding.get("weekly_change_pct"),
        "weekly_nav_impact_pct": holding.get("weekly_nav_impact_pct"),
    }


def _price_context_for_target(target: dict, priced: list[dict], official_nav: dict) -> dict:
    holding = next((item for item in priced if item.get("name") == target.get("name")), None)
    daily = []
    ticker = target.get("ticker")
    if holding:
        daily = holding.get("daily_changes") or []
        ticker = ticker or holding.get("ticker")
    elif target.get("type") == "sector":
        member_names = set(target.get("members") or [])
        combined = []
        for item in priced:
            if item.get("name") in member_names:
                combined.extend(item.get("daily_changes") or [])
        by_date = {}
        for row in combined:
            by_date.setdefault(row.get("date"), []).append(float(row.get("change_pct") or 0))
        daily = [
            {
                "date": date,
                "change_pct": round(sum(values) / len(values), 2),
            }
            for date, values in sorted(by_date.items())
        ]
    return {
        "ticker": ticker,
        "daily_changes": daily,
        "official_nav_change_pct": official_nav.get("change_pct"),
        "week_start": official_nav.get("start"),
        "week_end": official_nav.get("end"),
    }


def load_scrape_cache(out_dir: Path) -> dict[str, dict]:
    cache = {}
    if not out_dir.exists():
        return cache
    for path in out_dir.glob("*.json"):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for key in ("input_url", "resolved_url", "final_url"):
            url = record.get(key)
            if url:
                cache[url] = record
    return cache


def scrape_unique_articles(articles_by_link: dict[str, list[dict]], out_dir: Path) -> int:
    """Scrape each unique RSS link once and attach text onto all copies."""
    out_dir.mkdir(parents=True, exist_ok=True)
    links = [link for link in articles_by_link if link]
    if not links:
        return 0
    cache = load_scrape_cache(out_dir)

    def job(index_link):
        index, link = index_link
        cached = cache.get(link)
        if cached and (cached.get("text") or "").strip():
            return index, link, cached
        try:
            record = scrape_one(thread_session(), link, retries=2)
        except Exception as exc:
            record = {
                "input_url": link,
                "resolved_url": None,
                "text": "",
                "status": "fetch_failed",
                "error": str(exc),
            }
        return index, link, record

    scraped_ok = 0
    with ThreadPoolExecutor(max_workers=SCRAPE_WORKERS) as pool:
        futures = [pool.submit(job, item) for item in enumerate(links, start=1)]
        for future in as_completed(futures):
            index, link, record = future.result()
            resolved = record.get("resolved_url") or record.get("final_url")
            status = record.get("status") or "fetch_failed"
            text = record.get("text") or ""
            if resolved and not publisher_host_allowlisted(resolved):
                status = "publisher_blocked"
                text = ""
            elif status in {"ok", "extract_thin"} and text:
                scraped_ok += 1
                try:
                    _write_record(out_dir, index, record, save_html=True)
                except Exception as exc:
                    logger.warning("Could not write scrape dump for %s: %s", link, exc)
            for article in articles_by_link[link]:
                article["resolved_url"] = resolved
                article["text"] = text
                article["scrape_status"] = status
                article["scrape_error"] = record.get("error")

    return scraped_ok


def apply_causal_scores(target: dict, priced: list[dict], official_nav: dict) -> None:
    survivors = [
        article
        for article in target.get("articles") or []
        if article.get("scrape_status") in {"ok", "extract_thin"}
        and (article.get("text") or "").strip()
    ]
    for index, article in enumerate(survivors, start=1):
        article["article_id"] = index
    if not survivors:
        target["relevant_news"] = []
        target["scored_count"] = 0
        return

    price_context = _price_context_for_target(target, priced, official_nav)
    result = score_articles_causal(target, survivors, price_context)
    score_map = {item["article_id"]: item for item in result.get("scored_news") or []}
    scored_articles = []
    for article in survivors:
        scores = score_map.get(article["article_id"])
        if not scores:
            continue
        article.update(scores)
        if (
            float(article.get("causal_score") or 0) >= CAUSAL_SCORE_MIN
            and article.get("timing_plausible")
            and article_matches_move_sentiment(target, article)
        ):
            scored_articles.append(article)

    groups = group_by_event(scored_articles)
    target["relevant_news"] = select_final_events(groups)
    target["scored_count"] = len(scored_articles)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Weekly fund NAV news pipeline")
    fund_group = parser.add_mutually_exclusive_group()
    for fund_id in available_fund_ids():
        fund_group.add_argument(
            f"--{fund_id}",
            action="store_const",
            const=fund_id,
            dest="fund",
            help=f"Load holdings, NAV, and sectors from data/{fund_id}/",
        )
    parser.add_argument(
        "--resume-failed",
        action="store_true",
        help="Re-score names listed in RESUME_FAILED_NAMES",
    )
    return parser.parse_args(argv)


def result_json_path_for(fund_id: str | None) -> Path:
    if fund_id:
        return OUTPUT_SCRAPPER_DIR / fund_id / "result.json"
    return OUTPUT_SCRAPPER_DIR / "result.json"


def main(fund_id: str | None = None):
    clear_run_output_dirs()
    data_dir = resolve_fund_data_dir(fund_id)
    logger.info("Loading fund holdings, NAV history, and sectors from %s", data_dir)
    bundle = load_fund_bundle(data_dir)
    official_nav = bundle["official_nav"]
    price_universe = bundle["price_universe"]
    large_sectors = bundle["large_sectors"]
    official_change = official_nav["change_pct"]

    logger.info(
        "Official NAV week %s to %s (%s -> %s, %s%%)",
        official_nav["start"],
        official_nav["end"],
        official_nav["start_nav"],
        official_nav["end_nav"],
        official_change,
    )

    with contextlib.redirect_stdout(io.StringIO()):
        fund_result = get_fund_weekly_prices(
            fund_id or "Fund",
            price_universe,
            official_nav["start"],
            official_nav["end"],
        )

    priced = fund_result.get("holdings", [])
    skipped = fund_result.get("skipped", [])
    headline = sort_by_weekly_nav_impact(select_headline_holdings(priced))
    price_only = [
        _compact_price_only(item)
        for item in priced
        if float(item.get("nav_percentage") or 0) < MIN_HOLDING_PCT
    ]

    sector_moves = build_sector_moves(priced, large_sectors)
    news_targets = select_news_targets(headline, sector_moves, official_change)
    offsets = select_offsets(headline, official_change)
    drags = select_drags(headline, official_change)

    logger.info("Harvesting allowlisted Google News RSS for the NAV week...")
    total_harvested = 0
    articles_by_link = {}
    for target in news_targets:
        try:
            articles = fetch_news_for_week(
                target,
                official_nav["start"],
                official_nav["end"],
            )
        except Exception as exc:
            logger.error("News harvest failed for %s: %s", target.get("name"), exc)
            articles = []
        kept = filter_articles_by_keyword(
            articles,
            target.get("name") or "",
            target.get("industry") or "",
        )
        target["harvest_count"] = len(articles)
        target["keyword_count"] = len(kept)
        target["articles"] = kept
        total_harvested += len(articles)
        for article in kept:
            link = article.get("link") or ""
            if not link:
                article["text"] = ""
                article["scrape_status"] = "missing_link"
                continue
            articles_by_link.setdefault(link, []).append(article)
        logger.info(
            "  %s: harvested=%s keyword=%s",
            target.get("name"),
            len(articles),
            len(kept),
        )

    logger.info(
        "Scraping %s unique article URLs with %s workers...",
        len(articles_by_link),
        SCRAPE_WORKERS,
    )
    scraped_ok = scrape_unique_articles(articles_by_link, OUT_DIR)
    logger.info("Successful scrapes: %s / %s unique URLs", scraped_ok, len(articles_by_link))

    logger.info("Running DeepSeek V4 Flash causal scoring per news target...")
    for target in news_targets:
        try:
            apply_causal_scores(target, priced, official_nav)
        except Exception as exc:
            logger.error("Causal scoring failed for %s: %s", target.get("name"), exc)
            target["relevant_news"] = []
            target["scored_count"] = 0
        target["article_count"] = len(target.get("relevant_news") or [])
        # Keep result.json smaller: drop raw scraped copies after events are selected.
        target.pop("articles", None)
        logger.info(
            "  %s: events=%s (causal survivors=%s)",
            target.get("name"),
            target["article_count"],
            target.get("scored_count", 0),
        )

    approx_equity_impact_pct = round(
        sum(float(item.get("weekly_nav_impact_pct") or 0) for item in headline),
        3,
    )

    logger.info("Writing Phase 5 investor summary...")
    summary_facts = build_summary_facts(
        official_nav,
        approx_equity_impact_pct,
        drags,
        offsets,
        sector_moves,
        news_targets,
    )
    investor_summary = write_investor_summary(summary_facts)
    if investor_summary:
        logger.info("Investor summary ready (%s words)", len(investor_summary.split()))
    else:
        logger.warning("Investor summary was empty")

    result_json_path = result_json_path_for(fund_id)
    result_json_path.parent.mkdir(parents=True, exist_ok=True)
    result_json_path.write_text(
        json.dumps({"investor_summary": investor_summary.strip()}, indent=2, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )
    logger.info("Saved investor summary to %s", result_json_path)
    print(investor_summary.strip())


RESUME_FAILED_NAMES = {
    "Knowledge Realty Trust",
    "Embassy Office Parks REIT",
    "Pharmaceuticals & Biotechnology",
}


def resume_failed_targets(names: set[str], fund_id: str | None = None) -> None:
    """Re-harvest cached scrapes and Groq-score names that missed the daily quota."""
    result_json_path = result_json_path_for(fund_id)
    output = json.loads(result_json_path.read_text(encoding="utf-8"))
    bundle = load_fund_bundle(resolve_fund_data_dir(fund_id))
    official_nav = bundle["official_nav"]
    with contextlib.redirect_stdout(io.StringIO()):
        fund_result = get_fund_weekly_prices(
            fund_id or "Fund",
            bundle["price_universe"],
            official_nav["start"],
            official_nav["end"],
        )
    priced = fund_result.get("holdings", [])
    news_targets = output.get("news_targets") or []
    articles_by_link = {}
    selected = []
    for target in news_targets:
        if target.get("name") not in names:
            continue
        articles = fetch_news_for_week(target, official_nav["start"], official_nav["end"])
        kept = filter_articles_by_keyword(
            articles,
            target.get("name") or "",
            target.get("industry") or "",
        )
        target["harvest_count"] = len(articles)
        target["keyword_count"] = len(kept)
        target["articles"] = kept
        selected.append(target)
        for article in kept:
            link = article.get("link") or ""
            if not link:
                article["text"] = ""
                article["scrape_status"] = "missing_link"
                continue
            articles_by_link.setdefault(link, []).append(article)
        logger.info("Resume harvest %s: keyword=%s", target.get("name"), len(kept))

    scraped_ok = scrape_unique_articles(articles_by_link, OUT_DIR)
    logger.info("Resume scrapes (cache+fetch): %s / %s", scraped_ok, len(articles_by_link))
    for target in selected:
        apply_causal_scores(target, priced, official_nav)
        target["article_count"] = len(target.get("relevant_news") or [])
        target.pop("articles", None)
        logger.info(
            "  %s: events=%s (causal survivors=%s)",
            target.get("name"),
            target["article_count"],
            target.get("scored_count", 0),
        )

    output["news_targets"] = news_targets
    output["stock_moves"] = [t for t in news_targets if t.get("type") == "stock"]
    result_json_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        json.dumps(
            {
                "resumed": [t.get("name") for t in selected],
                "events": {t.get("name"): t.get("article_count") for t in selected},
                "result_path": str(result_json_path),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    args = parse_args()
    if args.resume_failed:
        resume_failed_targets(RESUME_FAILED_NAMES, args.fund)
    else:
        main(args.fund)
