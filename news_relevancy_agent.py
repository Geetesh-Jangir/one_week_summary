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
import requests

load_dotenv()

logger = logging.getLogger(__name__)

GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-flash")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")


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


CAUSAL_SYSTEM_PROMPT = """You are a financial analyst investigating WHY a stock or sector price moved.

Return a json object. For each article, decide whether it describes an event that CAUSED or CONTRIBUTED to the observed weekly price movement. Mentioning the ticker is not enough.

TARGET_SENTIMENT is the direction of the weekly price move for this name or sector:
- negative: the price fell. Only bearish events can explain that move.
- positive: the price rose. Only bullish events can explain that move.

Score each article on:
1. relevancy_score (0-10): Financial materiality to this company or sector. A beat/upgrade can still be relevant even if the stock fell.
2. causal_score (0-10): How likely this event CAUSED the observed weekly move.
   Give causal_score 0-3 if sentiment does not match TARGET_SENTIMENT
   (example: stock down, article about better performance / profit beat / upgrade).
   - 9-10: Almost certainly the primary catalyst for the observed direction
   - 7-8: Strong contributing factor in that direction
   - 5-6: Plausible but uncertain
   - 3-4: Weak, indirect, or wrong direction
   - 0-2: Unrelated to the price movement
3. event_label: A short 3-8 word tag for the UNDERLYING EVENT.
   Articles about the same real-world event MUST use the same event_label.
4. causal_link: "direct" | "sector" | "macro" | "none"
5. timing_plausible (true/false): Published BEFORE or ON the relevant move day.
6. sentiment: "positive" or "negative" — the price direction THIS STORY implies, not the fund NAV.
7. reasoning: 1-2 sentence causal explanation.

EXAMPLE JSON OUTPUT:
{
  "scores": [
    {
      "article_id": 1,
      "relevancy_score": 8,
      "causal_score": 9,
      "event_label": "RBI unsecured loan provisioning norms",
      "causal_link": "direct",
      "timing_plausible": true,
      "sentiment": "negative",
      "reasoning": "..."
    }
  ]
}
"""


CAUSAL_BATCH_SIZE = 8
CAUSAL_MAX_CHARS = 400
CAUSAL_MAX_TOKENS = 16000


def _first_chars(text: str, max_chars: int = CAUSAL_MAX_CHARS) -> str:
    raw = (text or "").strip()
    if len(raw) <= max_chars:
        return raw
    return raw[:max_chars].rstrip()


def _llm_json_chat(system_prompt: str, user_prompt: str, max_tokens: int = CAUSAL_MAX_TOKENS) -> dict:
    if not DEEPSEEK_API_KEY:
        raise RuntimeError("DEEPSEEK_API_KEY not configured")
    url = DEEPSEEK_BASE_URL.rstrip("/") + "/chat/completions"
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
        "thinking": {"type": "disabled"},
    }
    response = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=300,
    )
    if not response.ok:
        raise RuntimeError(f"DeepSeek HTTP {response.status_code}: {response.text[:500]}")
    message = (response.json().get("choices") or [{}])[0].get("message") or {}
    parsed = extract_json_from_text(message.get("content") or "")
    if parsed:
        return parsed
    raise ValueError("Invalid JSON response from DeepSeek")


def validate_causal_scores(response_data: dict, original_articles: list[dict]) -> list[dict]:
    if not isinstance(response_data, dict):
        return []
    scores = response_data.get("scores")
    if not isinstance(scores, list):
        return []
    original_ids = {article["article_id"] for article in original_articles}
    seen = set()
    valid = []
    allowed_links = {"direct", "sector", "macro", "none"}
    for item in scores:
        if not isinstance(item, dict):
            continue
        try:
            article_id = int(item.get("article_id"))
        except Exception:
            continue
        if article_id not in original_ids or article_id in seen:
            continue
        try:
            relevancy = max(0, min(10, int(item.get("relevancy_score", 0))))
        except Exception:
            relevancy = 0
        try:
            causal = max(0, min(10, int(item.get("causal_score", 0))))
        except Exception:
            causal = 0
        sentiment = str(item.get("sentiment") or "negative").strip().lower()
        if sentiment not in ("positive", "negative"):
            sentiment = "negative" if "neg" in sentiment else "positive"
        link = str(item.get("causal_link") or "none").strip().lower()
        if link not in allowed_links:
            link = "none"
        timing = item.get("timing_plausible")
        if isinstance(timing, str):
            timing = timing.strip().lower() in {"true", "yes", "1"}
        else:
            timing = bool(timing)
        seen.add(article_id)
        valid.append(
            {
                "article_id": article_id,
                "relevancy_score": relevancy,
                "causal_score": causal,
                "event_label": str(item.get("event_label") or "").strip(),
                "causal_link": link,
                "timing_plausible": timing,
                "sentiment": sentiment,
                "reasoning": str(item.get("reasoning") or "").strip(),
            }
        )
    return valid


def build_causal_user_prompt(target: dict, articles: list[dict], price_context: dict) -> str:
    daily = price_context.get("daily_changes") or []
    daily_lines = []
    for row in daily:
        daily_lines.append(f"  {row.get('date')}: {row.get('change_pct')}%")
    daily_block = "\n".join(daily_lines) if daily_lines else "  (none)"
    parts = []
    for article in articles:
        excerpt = _first_chars(article.get("text") or "", CAUSAL_MAX_CHARS)
        parts.append(
            f"--- Article {article['article_id']} (published: {article.get('published')}) ---\n"
            f"Title: {article.get('title')}\n"
            f"Text (first {CAUSAL_MAX_CHARS} characters): {excerpt}\n"
        )
    count = len(articles)
    wanted = target.get("target_sentiment") or "negative"
    return f"""Return json scores for every article below.

TARGET: {target.get('name')}
TYPE: {target.get('type')}
INDUSTRY: {target.get('industry')}
TICKER: {price_context.get('ticker') or ''}
WEEKLY CHANGE: {target.get('weekly_change_pct')}%
TARGET_SENTIMENT: {wanted}
OFFICIAL FUND NAV CHANGE: {price_context.get('official_nav_change_pct')}%
WEEK: {price_context.get('week_start')} to {price_context.get('week_end')}

DAILY PRICE BREAKDOWN:
{daily_block}

Score these {count} articles:
{chr(10).join(parts)}

Score all {count} articles as json. Assign the SAME event_label to articles about the same underlying event.
If TARGET_SENTIMENT is negative, do not give causal_score >= 5 to bullish performance/upgrade/beat stories.
If TARGET_SENTIMENT is positive, do not give causal_score >= 5 to bearish deterioration stories."""


def _score_causal_batch(target: dict, batch: list[dict], price_context: dict) -> list[dict]:
    if not batch:
        return []
    user_prompt = build_causal_user_prompt(target, batch, price_context)
    try:
        response_data = _llm_json_chat(CAUSAL_SYSTEM_PROMPT, user_prompt)
        return validate_causal_scores(response_data, batch)
    except Exception as exc:
        logger.error(
            "Causal scoring failed for %s (%s articles): %s",
            target.get("name"),
            len(batch),
            exc,
        )
        return []


def score_articles_causal(
    target: dict,
    articles: list[dict],
    price_context: dict,
    batch_size: int = CAUSAL_BATCH_SIZE,
) -> dict:
    """Causal scoring with event_label. DeepSeek batches of 8 articles, first 400 characters each."""
    if not articles:
        return {"scored_news": []}
    if not DEEPSEEK_API_KEY:
        logger.error("DEEPSEEK_API_KEY not set in environment")
        return {"scored_news": [], "error": "DEEPSEEK_API_KEY not configured"}

    scored = []
    for start in range(0, len(articles), batch_size):
        batch = articles[start : start + batch_size]
        scored.extend(_score_causal_batch(target, batch, price_context))
    return {"scored_news": scored}