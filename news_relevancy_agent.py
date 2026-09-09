"""
News Relevancy Agent - Determines the most relevant news for a company's stock.

Uses Groq LLM to rank news by relevance to instrument_name and industry.
"""

import json
import logging
import os
from typing import Optional

from groq import Groq

logger = logging.getLogger(__name__)

GROQ_MODEL = "openai/gpt-oss-120b"
GROQ_API_KEY = "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"


SYSTEM_PROMPT = """You are a financial news relevance-ranking agent. Your task is to identify the 2 news titles most relevant to a specific company's stock performance.

RELEVANCE PRIORITY:
1. COMPANY-SPECIFIC NEWS (Highest): Direct mentions of the company - earnings, revenue, management changes, regulatory actions, M&A, dividends, analyst ratings, major contracts, fraud/scandals, shareholder activity, etc.
2. INDUSTRY/SECTOR NEWS (Secondary): Industry-wide regulations, policy changes, sector trends - ONLY if they could materially impact the specific company.
3. GENERAL MARKET NEWS (Low): Broad market movements, unrelated companies, commodities, macro news without clear company connection.

Return ONLY valid JSON with exactly this structure:
{
  "relevant_news": [
    {"title": "exact original title 1"},
    {"title": "exact original title 2"}
  ]
}

Rules:
- Return exactly 2 titles (or fewer if less than 2 valid inputs)
- Titles MUST be exact matches from the provided input list
- No explanations, no markdown, no extra text
- If uncertain, prefer company-specific over industry news
- If multiple company-specific news exist, prioritize by potential stock impact"""


def build_user_prompt(
    instrument_name: str, industry: str, news_titles: list[str]
) -> str:
    """Build the user prompt with company, industry, and news titles."""
    titles_json = json.dumps(news_titles, ensure_ascii=False)
    return f"""Instrument: {instrument_name}
Industry: {industry}

News Titles:
{titles_json}

Return the top 2 most relevant news titles for this company's stock."""


def validate_response(response_data: dict, original_titles: list[str]) -> list[dict]:
    """Validate and filter LLM response to ensure only original titles are returned."""
    if not isinstance(response_data, dict):
        logger.warning("LLM response is not a dict")
        return []

    relevant_news = response_data.get("relevant_news")
    if not isinstance(relevant_news, list):
        logger.warning("LLM response missing 'relevant_news' list")
        return []

    valid_results = []
    original_set = set(original_titles)

    for item in relevant_news:
        if not isinstance(item, dict):
            continue
        title = item.get("title")
        if not isinstance(title, str):
            continue
        if title in original_set:
            valid_results.append({"title": title})
        else:
            logger.warning(f"LLM returned invalid title not in input: {title[:100]}")

    return valid_results[:2]


def get_most_relevant_news(
    instrument_name: str,
    industry: str,
    news_titles: list[str],
    model: Optional[str] = None,
) -> dict:
    """
    Get the top 2 most relevant news titles for a company's stock.

    Args:
        instrument_name: Company/instrument name (e.g., "ICICI Bank")
        industry: Industry/sector (e.g., "Banking")
        news_titles: List of news title strings
        model: Optional Groq model override

    Returns:
        Dict with "relevant_news" list containing up to 2 title objects
    """
    if not news_titles:
        logger.info("No news titles provided")
        return {"relevant_news": []}

    if not GROQ_API_KEY:
        logger.error("GROQ_API_KEY not set in environment")
        return {"relevant_news": [], "error": "GROQ_API_KEY not configured"}

    try:
        client = Groq(api_key=GROQ_API_KEY)
    except Exception as e:
        logger.error(f"Failed to initialize Groq client: {e}")
        return {"relevant_news": [], "error": f"Groq client error: {e}"}

    model_name = model or GROQ_MODEL
    user_prompt = build_user_prompt(instrument_name, industry, news_titles)

    try:
        completion = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            max_tokens=500,
            response_format={"type": "json_object"},
        )
    except Exception as e:
        logger.error(f"Groq API call failed: {e}")
        return {"relevant_news": [], "error": f"API error: {e}"}

    try:
        response_text = completion.choices[0].message.content
        response_data = json.loads(response_text)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM JSON response: {e}")
        return {"relevant_news": [], "error": f"Invalid JSON from LLM: {e}"}
    except Exception as e:
        logger.error(f"Unexpected error parsing LLM response: {e}")
        return {"relevant_news": [], "error": f"Response parse error: {e}"}

    valid_news = validate_response(response_data, news_titles)
    return {"relevant_news": valid_news}
