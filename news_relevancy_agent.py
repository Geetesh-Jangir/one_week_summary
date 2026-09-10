"""
News Relevancy & Sentiment Agent - Scores news titles for relevance (0-10) and sentiment (positive/negative) to a company's stock.
"""

import json
import logging
import os
import re
from typing import Optional

from dotenv import load_dotenv
from groq import Groq

load_dotenv()

logger = logging.getLogger(__name__)

GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")


SYSTEM_PROMPT = """You are a financial analyst agent. Score each news headline for its relevance (0-10) and sentiment (positive or negative) regarding a specific company's stock performance.

RELEVANCY SCORE (0 to 10):
10 = Direct company earnings/merger/fraud/legal/regulatory action with major stock price impact.
8-9 = Significant company development or major sector policy directly affecting the company.
5-7 = Moderate connection or modest price impact.
0-4 = Minimal or irrelevant connection, generic macro news, or unrelated stories.

SENTIMENT ("positive" or "negative"):
- "negative": If the news title implies the stock price is likely to go DOWN (e.g. profit drop, penalties, litigation, rating downgrade, executive exit, headwinds).
- "positive": If the news title implies the stock price is likely to go UP (e.g. profit surge, contract win, rating upgrade, buyback, favorable approval).

OUTPUT FORMAT:
Return JSON with the key "scores" containing an array of objects for all input articles:
{
  "scores": [
    {"article_id": 1, "relevancy_score": 9, "sentiment": "negative"}
  ]
}
"""


def build_user_prompt(
    instrument_name: str, industry: str, articles: list[dict]
) -> str:
    """Build the user prompt containing company, industry, and article titles only."""
    titles_payload = [
        {"article_id": a["article_id"], "title": a["title"]}
        for a in articles
    ]
    articles_json = json.dumps(titles_payload, ensure_ascii=False, indent=2)
    count = len(articles)
    return f"""Target Instrument: {instrument_name}
Industry: {industry}

List of {count} news titles to evaluate:
{articles_json}

Evaluate all {count} articles. Return JSON with "scores" containing exactly {count} objects matching each article_id from 1 to {count}."""


def extract_json_from_text(text: str) -> Optional[dict]:
    """Attempt to extract and parse JSON object from LLM response text."""
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        pass

    # Try regex match for JSON markdown block or outermost {...}
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except Exception:
            pass

    match = re.search(r"(\{.*\})", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except Exception:
            pass

    return None


def validate_scores_response(
    response_data: dict, original_articles: list[dict]
) -> list[dict]:
    """Validate LLM response and return list of valid score objects."""
    if not isinstance(response_data, dict):
        logger.warning("LLM response is not a dict")
        return []

    scores = response_data.get("scores")
    if not isinstance(scores, list):
        logger.warning("LLM response missing 'scores' list")
        return []

    original_ids = {a["article_id"] for a in original_articles}
    seen_ids = set()
    valid_scores = []

    for item in scores:
        if not isinstance(item, dict):
            continue

        article_id = item.get("article_id")
        score = item.get("relevancy_score")
        sentiment = item.get("sentiment")

        if not isinstance(article_id, int):
            try:
                article_id = int(article_id)
            except Exception:
                continue

        if article_id not in original_ids or article_id in seen_ids:
            continue

        if not isinstance(score, (int, float)):
            try:
                score = int(score)
            except Exception:
                score = 0

        score_int = max(0, min(10, int(score)))

        sentiment_str = str(sentiment).strip().lower() if sentiment else "negative"
        if sentiment_str not in ("positive", "negative"):
            sentiment_str = "negative" if "neg" in sentiment_str else "positive"

        seen_ids.add(article_id)
        valid_scores.append({
            "article_id": article_id,
            "relevancy_score": score_int,
            "sentiment": sentiment_str,
        })

    missing_ids = original_ids - seen_ids
    if missing_ids:
        logger.warning(f"LLM did not return scores for article_ids: {sorted(missing_ids)}")

    return valid_scores


def score_news_relevance(
    instrument_name: str,
    industry: str,
    articles: list[dict],
    model: Optional[str] = None,
) -> dict:
    """
    Score news articles (titles) for relevance (0-10) and sentiment (positive/negative).
    """
    if not articles:
        return {"scored_news": []}

    if not GROQ_API_KEY:
        logger.error("GROQ_API_KEY not set in environment")
        return {"scored_news": [], "error": "GROQ_API_KEY not configured"}

    try:
        client = Groq(api_key=GROQ_API_KEY)
    except Exception as e:
        logger.error(f"Failed to initialize Groq client: {e}")
        return {"scored_news": [], "error": f"Groq client error: {e}"}

    model_name = model or GROQ_MODEL
    user_prompt = build_user_prompt(instrument_name, industry, articles)

    response_text = ""
    # 1. Try with JSON object mode
    try:
        completion = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            max_tokens=3000,
            response_format={"type": "json_object"},
        )
        response_text = completion.choices[0].message.content
    except Exception as e:
        logger.warning(f"Groq API JSON mode failed ({e}), retrying without strict json_object mode...")
        # 2. Fallback without strict response_format
        try:
            completion = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
                max_tokens=3000,
            )
            response_text = completion.choices[0].message.content
        except Exception as e2:
            logger.error(f"Groq API call completely failed: {e2}")
            return {"scored_news": [], "error": f"API error: {e2}"}

    response_data = extract_json_from_text(response_text)
    if not response_data:
        logger.error(f"Failed to parse valid JSON from LLM response: {response_text[:200]}")
        return {"scored_news": [], "error": "Invalid JSON response"}

    valid_scores = validate_scores_response(response_data, articles)
    return {"scored_news": valid_scores}