"""
News Relevancy Agent - Scores news articles for relevance to a company's stock.

Uses Groq LLM to independently score each article 0-10, then filters for >= 8.
"""

import json
import logging
import os
from typing import Optional

from dotenv import load_dotenv
from groq import Groq

load_dotenv()

logger = logging.getLogger(__name__)

GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")


SYSTEM_PROMPT = """You are a financial news relevance-scoring agent. Your task is to independently score each news article for its relevance to a specific company's stock performance.

SCORING RUBRIC (0-10):

10 = Extremely relevant. Direct company-specific event with very high potential to materially affect stock performance.
9  = Very highly relevant. Direct company-specific development with strong potential stock impact.
8  = Highly relevant. Meaningful company-specific or major industry event that could materially affect the company.
7  = Relevant. Clear relationship to the company or industry, but expected stock impact is moderate or uncertain.
6  = Moderately relevant. Some meaningful connection but limited expected stock impact.
5  = Neutral/moderate relevance. Related to the company/industry but weak or unclear investment impact.
4  = Low relevance. Peripheral connection.
3  = Very low relevance. Weak relationship to the company or investment thesis.
2  = Barely relevant. Mostly unrelated or only loosely connected.
1  = Almost irrelevant.
0  = Completely irrelevant to the company's stock.

HIGH RELEVANCE EXAMPLES (score 8-10):
- Earnings, profit/revenue changes
- Management changes
- Major regulatory action (RBI, SEBI, etc.) directly affecting the company
- M&A activity involving the company
- Major contracts/orders
- Dividends, buybacks, capital raising
- Fraud/scandal involving the company
- Major legal action
- Major analyst downgrade/upgrade
- Major shareholder activity
- Significant product/business event
- Major sector regulation that materially affects the company

LOW RELEVANCE EXAMPLES (score 0-4):
- Unrelated company news
- Generic market commentary
- Generic financial education articles
- Articles about another company with no meaningful connection
- Minor market movements
- Repetitive/duplicate stories
- Generic macro news without clear company connection

SCORING RULES:
- Score EVERY article independently. Do NOT rank articles relative to one another.
- Do NOT increase or decrease a score because another article is more/less relevant.
- Evaluate each article using: company name, industry, article title, article description.
- Company-specific news generally scores higher when potential stock impact is material.
- Industry news scores higher only if it could materially impact the specific company.

Return ONLY valid JSON with exactly this structure:
{
  "scores": [
    {"article_id": 1, "relevancy_score": 9},
    {"article_id": 2, "relevancy_score": 4},
    {"article_id": 3, "relevancy_score": 8}
  ]
}

Rules:
- Return exactly one score object per input article
- article_id must match the input article_id
- relevancy_score must be an integer 0-10
- No explanations, no markdown, no extra text"""


def build_user_prompt(
    instrument_name: str, industry: str, articles: list[dict]
) -> str:
    """Build the user prompt with company, industry, and articles to score."""
    articles_json = json.dumps(articles, ensure_ascii=False, indent=2)
    return f"""Instrument: {instrument_name}
Industry: {industry}

Articles to score independently:
{articles_json}

Score each article independently 0-10. Return JSON with "scores" array."""


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

        if not isinstance(article_id, int):
            logger.warning(f"Invalid article_id type: {article_id}")
            continue
        if article_id not in original_ids:
            logger.warning(f"LLM returned score for unknown article_id: {article_id}")
            continue
        if article_id in seen_ids:
            logger.warning(f"Duplicate article_id in LLM response: {article_id}")
            continue
        if not isinstance(score, (int, float)):
            logger.warning(f"Invalid score type for article_id {article_id}: {score}")
            continue

        score_int = int(score)
        if not (0 <= score_int <= 10):
            logger.warning(f"Score out of range 0-10 for article_id {article_id}: {score}")
            continue

        seen_ids.add(article_id)
        valid_scores.append({"article_id": article_id, "relevancy_score": score_int})

    # Check for missing articles
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
    Score news articles for relevance to a company's stock.

    Args:
        instrument_name: Company/instrument name (e.g., "ICICI Bank")
        industry: Industry/sector (e.g., "Banking")
        articles: List of article dicts with at least 'article_id', 'title', 'description', 'link', 'news_type'
        model: Optional Groq model override

    Returns:
        Dict with "relevant_news" list containing articles with score >= 8,
        sorted by score descending. Each item has title, link, relevancy_score.
    """
    if not articles:
        logger.info("No articles provided for scoring")
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
    user_prompt = build_user_prompt(instrument_name, industry, articles)

    try:
        completion = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            max_tokens=1000,
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

    valid_scores = validate_scores_response(response_data, articles)

    # Build article_id -> original article mapping
    article_by_id = {a["article_id"]: a for a in articles}

    # Join scores with original articles and filter >= 8
    relevant_news = []
    for score_obj in valid_scores:
        article_id = score_obj["article_id"]
        score = score_obj["relevancy_score"]

        if score >= 8:
            original = article_by_id[article_id]
            relevant_news.append({
                "title": original["title"],
                "link": original.get("link", ""),
                "relevancy_score": score
            })

    # Sort by score descending
    relevant_news.sort(key=lambda x: x["relevancy_score"], reverse=True)

    logger.info(f"Scored {len(articles)} articles, {len(relevant_news)} >= 8 threshold")
    return {"relevant_news": relevant_news}