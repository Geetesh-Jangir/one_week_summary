"""
Main entry point: Fetch top 3 holdings by NAV impact and their relevant news.

Flow:
1. Get fund holdings with price data and NAV impact (from demo.py)
2. Select top 3 by NAV impact (from stocks_for_news.py)
3. For each holding, fetch instrument + industry news (from app.py)
4. Score news relevance using LLM (from news_relevancy_agent.py)
5. Combine and output JSON sorted by nav_impact_percentage descending
"""

import json
import logging
import sys
import io
import contextlib
from pathlib import Path

from demo import get_fund_top_10_prices
from stocks_for_news import get_top_3_nav_impact_holdings
from app import fetch_news_for_dates
from news_relevancy_agent import score_news_relevance
from lib.fetch import thread_session
from web_scrapper import scrape_one, _write_record

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "out"
OUTPUT_SCRAPPER_DIR = ROOT / "output-scrapper"


def sort_by_nav_impact(holdings: list[dict]) -> list[dict]:
    """
    Sort holdings by nav_impact_percentage:
    - Negative values: ascending (most negative first)
    - Positive values: descending (highest positive first)
    """
    negative = [h for h in holdings if h["nav_impact_percentage"] < 0]
    positive = [h for h in holdings if h["nav_impact_percentage"] >= 0]

    negative.sort(key=lambda x: x["nav_impact_percentage"])  # ascending: -0.21, -0.061, -0.052
    positive.sort(key=lambda x: x["nav_impact_percentage"], reverse=True)  # descending: 0.5, 0.3, 0.1

    return negative + positive


def fetch_and_score_news(
    holding: dict,
    target_sentiment: str,
    min_relevancy_score: int = 5,
) -> list[dict]:
    """
    Fetch news for a holding from last 3 days (10 from 2 days ago, 10 from 1 day ago),
    score for relevance and sentiment, and return top 3 articles matching target_sentiment
    with relevancy_score strictly above min_relevancy_score (relevancy_score > 5).
    """
    instrument_name = holding["name"]
    industry = holding["industry"]

    logger.info(
        f"Processing news for: {instrument_name} (industry: {industry}) "
        f"[target sentiment: {target_sentiment}, min relevancy: >{min_relevancy_score}]"
    )

    try:
        # fetch_news_for_dates collects up to 10 from 2 days ago and 10 from 1 day ago
        scored_news = fetch_news_for_dates(
            instrument_name=instrument_name,
            industry=industry,
            max_per_date=10,
        )

        # Filter by target sentiment ("negative" or "positive") and score strictly above 5
        matching_news = [
            article
            for article in scored_news
            if article.get("sentiment", "").lower() == target_sentiment.lower()
            and article.get("relevancy_score", 0) > min_relevancy_score
        ]

        # Sort by relevancy_score descending (with published date as tiebreaker)
        matching_news.sort(
            key=lambda x: (-x.get("relevancy_score", 0), x.get("published", ""))
        )

        # Select top 3 news articles
        top_3_news = matching_news[:3]
        logger.info(
            f"Found {len(matching_news)} articles with {target_sentiment} sentiment and score > {min_relevancy_score} "
            f"for {instrument_name}, selected top {len(top_3_news)}"
        )
        return top_3_news
    except Exception as e:
        logger.error(f"Error fetching/scoring news for {instrument_name}: {e}")
        return []


def process_holdings(holdings: list[dict], average_impact: float) -> list[dict]:
    """
    Process each holding: fetch news, filter by sentiment matching average_impact sign,
    and attach top 3 relevant news to each holding.
    """
    target_sentiment = "negative" if average_impact < 0 else "positive"
    logger.info(f"Fund average signed NAV impact is {average_impact} -> Target sentiment: {target_sentiment}")

    result = []
    for holding in holdings:
        try:
            relevant_news = fetch_and_score_news(holding, target_sentiment)
        except Exception as e:
            logger.error(f"Failed to process news for {holding.get('name')}: {e}")
            relevant_news = []

        holding_with_news = {
            "name": holding["name"],
            "industry": holding["industry"],
            "nav_percentage": holding["nav_percentage"],
            "ticker": holding["ticker"],
            "change_percentage": holding["change_percentage"],
            "nav_impact_percentage": holding["nav_impact_percentage"],
            "relevant_news": relevant_news,
        }
        result.append(holding_with_news)
    return result


def scrape_relevant_articles(holdings: list[dict], out_dir: Path = OUT_DIR) -> list[dict]:
    """
    For each relevant news article across all holdings, resolve Google News URL,
    scrape publisher full article text, save JSON & HTML to out_dir,
    and store scraped text in the article object.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    session = thread_session()
    article_index = 1

    for holding in holdings:
        holding_name = holding.get("name", "Unknown")
        news_items = holding.get("relevant_news", [])
        for article in news_items:
            link = article.get("link")
            title = article.get("title", "")
            if not link:
                article["text"] = ""
                continue

            logger.info(f"Scraping full text for [{holding_name}]: {title[:60]}...")
            try:
                record = scrape_one(session, link, retries=2)
                article["text"] = record.get("text", "")
                if record.get("resolved_url"):
                    article["resolved_url"] = record.get("resolved_url")
                
                # Save scraped record to out folder
                saved_json, saved_html = _write_record(out_dir, article_index, record, save_html=True)
                logger.info(f"Saved scraped article #{article_index} to {saved_json.name}")
                article_index += 1
            except Exception as e:
                logger.error(f"Failed to scrape article {link}: {e}")
                article["text"] = ""

    return holdings


def main():
    fund_name = "Fund Name"
    rows = [
        {
            "name": "HDFC Bank Ltd",
            "detail": "Financial Services",
            "percentage": "9.31%",
        },
        {
            "name": "ICICI Bank Ltd",
            "detail": "Financial Services",
            "percentage": "8.19%",
        },
        {
            "name": "Reliance Industries Ltd",
            "detail": "Energy",
            "percentage": "4.2%",
        },
        {
            "name": "Axis Bank Ltd",
            "detail": "Financial Services",
            "percentage": "4.06%",
        },
        {
            "name": "Bajaj Finance Ltd",
            "detail": "Financial Services",
            "percentage": "3.52%",
        },
        {
            "name": "Larsen & Toubro Ltd",
            "detail": "Industrials",
            "percentage": "3.47%",
        },
        {
            "name": "GE Vernova T&D India Ltd",
            "detail": "Industrials",
            "percentage": "2.81%",
        },
        {
            "name": "Sun Pharmaceuticals Industries Ltd",
            "detail": "Healthcare",
            "percentage": "2.8%",
        },
        {
            "name": "Infosys Ltd",
            "detail": "Technology",
            "percentage": "2.72%",
        },
        {
            "name": "Hindustan Unilever Ltd",
            "detail": "Consumer Defensive",
            "percentage": "2.71%",
        },
        {
            "name": "ITC Ltd",
            "detail": "Consumer Defensive",
            "percentage": "2.5%",
        },
        {
            "name": "Maruti Suzuki India Ltd",
            "detail": "Consumer Cyclical",
            "percentage": "2.44%",
        },
        {
            "name": "Mahindra & Mahindra Ltd",
            "detail": "Consumer Cyclical",
            "percentage": "2.35%",
        },
    ]

    logger.info("Fetching fund top 10 holdings with price data...")
    # Suppress demo.py print statements
    with contextlib.redirect_stdout(io.StringIO()):
        fund_result = get_fund_top_10_prices(fund_name, rows)

    average_impact = fund_result.get("average_signed_nav_impact", 0)
    logger.info(f"Average Signed NAV Impact: {average_impact}")

    logger.info("Selecting top 3 holdings by NAV impact...")
    top_3 = get_top_3_nav_impact_holdings(fund_result)

    if not top_3:
        logger.warning("No holdings found with NAV impact")
        print(json.dumps([], indent=2))
        return

    logger.info(f"Processing {len(top_3)} holdings...")
    holdings_with_news = process_holdings(top_3, average_impact)

    holdings_with_news = sort_by_nav_impact(holdings_with_news)

    logger.info("Scraping full article content for relevant news links...")
    holdings_with_news = scrape_relevant_articles(holdings_with_news, OUT_DIR)

    OUTPUT_SCRAPPER_DIR.mkdir(parents=True, exist_ok=True)
    result_json_path = OUTPUT_SCRAPPER_DIR / "result.json"
    result_json_str = json.dumps(holdings_with_news, indent=2, ensure_ascii=False)
    result_json_path.write_text(result_json_str, encoding="utf-8")
    logger.info(f"Saved complete result JSON to {result_json_path}")

    print(result_json_str)


if __name__ == "__main__":
    main()