"""
Main entry point: weekly prices, news targets, and allowlisted RSS (Phase 3).

Scraping and Groq scoring are not run in this phase.
"""

import json
import logging
import io
import contextlib
from pathlib import Path

from fund_data import MIN_HOLDING_PCT, load_fund_bundle
from demo import get_fund_weekly_prices
from stocks_for_news import (
    build_sector_moves,
    headline_holdings as select_headline_holdings,
    select_drags,
    select_news_targets,
    select_offsets,
)
from app import fetch_news_for_week

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent
OUTPUT_SCRAPPER_DIR = ROOT / "output-scrapper"


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


def main():
    logger.info("Loading fund holdings, NAV history, and sectors from data/")
    bundle = load_fund_bundle()
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
    logger.info(
        "Pricing %s equity/REIT names (>=2%% plus peers in >=3%% domestic sectors)",
        len(price_universe),
    )

    with contextlib.redirect_stdout(io.StringIO()):
        fund_result = get_fund_weekly_prices(
            "Fund",
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

    approx_equity_impact_pct = round(
        sum(float(item.get("weekly_nav_impact_pct") or 0) for item in headline),
        3,
    )
    if headline:
        average_signed = round(
            sum(float(item.get("weekly_nav_impact_pct") or 0) for item in headline)
            / len(headline),
            3,
        )
    else:
        average_signed = 0.0

    sector_moves = build_sector_moves(priced, large_sectors)
    news_targets = select_news_targets(headline, sector_moves, official_change)
    offsets = select_offsets(headline, official_change)
    drags = select_drags(headline, official_change)
    stock_moves = [target for target in news_targets if target.get("type") == "stock"]

    logger.info(
        "Priced %s names (%s >=2%%, %s peers), skipped %s",
        len(priced),
        len(headline),
        len(price_only),
        len(skipped),
    )
    logger.info(
        "Approx >=2%% equity impact %s%% vs official NAV %s%%",
        approx_equity_impact_pct,
        official_change,
    )
    logger.info(
        "News targets: %s (%s sector, %s stock); offsets: %s; drags: %s",
        len(news_targets),
        sum(1 for item in news_targets if item.get("type") == "sector"),
        len(stock_moves),
        len(offsets),
        len(drags),
    )
    for target in news_targets:
        logger.info(
            "  [%s] %s scope=%s sentiment=%s change=%s",
            target.get("type"),
            target.get("name"),
            target.get("scope"),
            target.get("target_sentiment"),
            target.get("weekly_change_pct"),
        )

    logger.info("Harvesting allowlisted Google News RSS for the NAV week...")
    total_articles = 0
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
        target["articles"] = articles
        target["article_count"] = len(articles)
        total_articles += len(articles)
        logger.info(
            "  harvested %s articles for %s",
            len(articles),
            target.get("name"),
        )
    logger.info("Total allowlisted week articles: %s", total_articles)

    output = {
        "week": {
            "start": official_nav["start"],
            "end": official_nav["end"],
        },
        "official_nav": official_nav,
        "approx_equity_impact_pct": approx_equity_impact_pct,
        "average_signed_nav_impact": average_signed,
        "holdings": headline,
        "price_only": price_only,
        "skipped": skipped,
        "sectors": [
            {
                "sector": row["sector"],
                "percentage": row["percentage"],
                "overseas": row["overseas"],
            }
            for row in large_sectors
        ],
        "sector_moves": sector_moves,
        "stock_moves": stock_moves,
        "offsets": offsets,
        "drags": drags,
        "news_targets": news_targets,
    }

    OUTPUT_SCRAPPER_DIR.mkdir(parents=True, exist_ok=True)
    result_json_path = OUTPUT_SCRAPPER_DIR / "result.json"
    result_json_str = json.dumps(output, indent=2, ensure_ascii=False)
    result_json_path.write_text(result_json_str, encoding="utf-8")
    logger.info("Saved Phase 3 result JSON to %s", result_json_path)
    summary = {
        "week": output["week"],
        "official_nav": official_nav,
        "approx_equity_impact_pct": approx_equity_impact_pct,
        "news_targets": [
            {
                "type": target.get("type"),
                "name": target.get("name"),
                "scope": target.get("scope"),
                "target_sentiment": target.get("target_sentiment"),
                "article_count": target.get("article_count", 0),
            }
            for target in news_targets
        ],
        "total_articles": total_articles,
        "result_path": str(result_json_path),
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
