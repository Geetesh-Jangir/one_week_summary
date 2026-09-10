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

from demo import get_fund_top_10_prices
from stocks_for_news import get_top_3_nav_impact_holdings
from app import fetch_news_for_dates
from news_relevancy_agent import score_news_relevance

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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


def fetch_and_score_news(holding: dict) -> list[dict]:
    """
    Fetch news for a holding from last 3 days, filter by date (2 days ago, 1 day ago),
    score for relevance, and return top 2 articles per date (score >= 8).
    Returns a flat list of articles with date, published, and relevancy_score.
    """
    instrument_name = holding["name"]
    industry = holding["industry"]

    logger.info(f"Processing news for: {instrument_name} (industry: {industry})")

    try:
        # fetch_news_for_dates handles: fetching, date filtering, scoring, threshold >= 8, top 2 per date
        # Using max_per_date=3 to stay within Groq token limits (3 * 2 sources * 2 dates = 12 articles max)
        relevant_news = fetch_news_for_dates(
            instrument_name=instrument_name,
            industry=industry,
            max_per_date=3,
            min_relevancy_score=8,
            top_per_date=2,
        )
        logger.info(f"Found {len(relevant_news)} relevant articles for {instrument_name}")
        return relevant_news
    except Exception as e:
        logger.error(f"Error scoring news for {instrument_name}: {e}")
        return []


def process_holdings(holdings: list[dict]) -> list[dict]:
    """
    Process each holding: fetch news, score relevance, attach to holding.
    Returns holdings with relevant_news field added.
    """
    result = []
    for holding in holdings:
        try:
            relevant_news = fetch_and_score_news(holding)
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

    logger.info("Selecting top 3 holdings by NAV impact...")
    top_3 = get_top_3_nav_impact_holdings(fund_result)

    if not top_3:
        logger.warning("No holdings found with NAV impact")
        print(json.dumps([], indent=2))
        return

    logger.info(f"Processing {len(top_3)} holdings...")
    holdings_with_news = process_holdings(top_3)

    holdings_with_news = sort_by_nav_impact(holdings_with_news)

    print(json.dumps(holdings_with_news, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()