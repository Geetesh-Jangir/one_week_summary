"""
Generate Google News RSS search URLs for a specific holding from
data.top_holdings, looked up interactively by instrument name.

Flow:
  1. Ask the user for an instrument name.
  2. Check whether that instrument name exists in top_holdings.
     - If not found -> tell the user it wasn't found.
  3. If found, check the `industry` field.
     - If industry is null/empty -> say we can't create URLs (skip).
     - If industry is present -> build both the instrument URL and the
       industry URL.

URL pattern:
    https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en
"""

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from html import unescape
from urllib.parse import quote_plus, urlparse

import feedparser
import requests

from news_relevancy_agent import score_news_relevance

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_URL = "https://news.google.com/rss/search"

# Prefixed onto the industry text before building its query,
# e.g. "Banks" -> "Indian Banks"
INDUSTRY_PREFIX = "Indian"

# IST timezone (Asia/Kolkata)
IST = timezone(timedelta(hours=5, minutes=30))

# Sample data matching the structure you shared.
SAMPLE_DATA = {
    "data": {
        "top_holdings": [
            {
                "instrument_name": "ICICI BANK LTD.",
                "percentage": 4,
                "fund_count": 3,
                "industry": "Banks",
                "isin": None,
            },
            {
                "instrument_name": "Max Healthcare Institute Limited",
                "percentage": 3.11,
                "fund_count": 1,
                "industry": "Healthcare Services",
                "isin": None,
            },
            {
                "instrument_name": "Eternal Limited",
                "percentage": 2.96,
                "fund_count": 1,
                "industry": "Retailing",
                "isin": None,
            },
            {
                "instrument_name": "InterGlobe Aviation Limited",
                "percentage": 2.87,
                "fund_count": 1,
                "industry": "Transport Services",
                "isin": None,
            },
            {
                "instrument_name": "Trent Limited",
                "percentage": 1.93,
                "fund_count": 1,
                "industry": "Retailing",
                "isin": None,
            },
            {
                "instrument_name": "Sai Life Sciences Limited",
                "percentage": 1.9,
                "fund_count": 1,
                "industry": "Pharmaceuticals & Biotechnology",
                "isin": None,
            },
            {
                "instrument_name": "Prestige Estates Projects Limited",
                "percentage": 1.86,
                "fund_count": 1,
                "industry": "Realty",
                "isin": None,
            },
            {
                "instrument_name": "Cash and Cash Equivalents",
                "percentage": 1.59,
                "fund_count": 3,
                "industry": None,
                "isin": None,
            },
            {
                "instrument_name": "ABB India Limited",
                "percentage": 1.54,
                "fund_count": 1,
                "industry": "Electrical Equipment",
                "isin": None,
            },
            {
                "instrument_name": "L&T FINANCE LTD",
                "percentage": 1.37,
                "fund_count": 2,
                "industry": "Finance",
                "isin": None,
            },
            {
                "instrument_name": "Cash and Cash Equivalents",
                "percentage": 1.59,
                "fund_count": 3,
                "industry": "null",
                "isin": "null",
            },
        ]
    }
}


def build_news_url(query: str) -> str:
    """Build a Google News RSS search URL for a given query string."""
    encoded_query = quote_plus(query)
    return f"{BASE_URL}?q={encoded_query}&hl=en-IN&gl=IN&ceid=IN:en"


def build_news_url_with_date(query: str, days_back: int = 3) -> str:
    """Build a Google News RSS search URL with date restriction."""
    encoded_query = quote_plus(f"{query} when:{days_back}d")
    return f"{BASE_URL}?q={encoded_query}&hl=en-IN&gl=IN&ceid=IN:en"


def find_holding(top_holdings: list, name: str):
    """
    Look up a holding by instrument_name (case-insensitive).
    Falls back to a substring match if there's exactly one candidate.
    Returns the holding dict, or None if not found / ambiguous.
    """
    target = name.strip().lower()

    # 1. Exact (case-insensitive) match
    for holding in top_holdings:
        instrument = (holding.get("instrument_name") or "").lower()
        if instrument == target:
            return holding

    # 2. Fallback: unique substring match
    candidates = [
        h for h in top_holdings if target in (h.get("instrument_name") or "").lower()
    ]
    if len(candidates) == 1:
        return candidates[0]

    return None


def generate_urls_for_holding(holding: dict) -> dict:
    """
    Build the instrument URL and (if industry is present) the industry URL
    for a single holding dict.
    """
    instrument_name = holding.get("instrument_name")
    industry = holding.get("industry")

    result = {
        "instrument_name": instrument_name,
        "industry": industry,
        "instrument_news_url": (
            build_news_url(instrument_name) if instrument_name else None
        ),
        "industry_news_url": None,
    }

    if industry:
        result["industry_news_url"] = build_news_url(f"{INDUSTRY_PREFIX} {industry}")

    return result


def generate_date_filtered_urls_for_holding(holding: dict) -> dict:
    """
    Build the instrument URL and (if industry is present) the industry URL
    with date filter (when:3d) for a single holding dict.
    """
    instrument_name = holding.get("instrument_name")
    industry = holding.get("industry")

    result = {
        "instrument_name": instrument_name,
        "industry": industry,
        "instrument_news_url": (
            build_news_url_with_date(instrument_name) if instrument_name else None
        ),
        "industry_news_url": None,
    }

    if industry:
        result["industry_news_url"] = build_news_url_with_date(f"{INDUSTRY_PREFIX} {industry}")

    return result


def _clean_html_text(text: str) -> str:
    """Remove HTML tags and decode HTML entities from text."""
    if not text:
        return ""
    # Remove HTML tags
    clean = re.sub(r"<[^>]+>", "", text)
    # Decode HTML entities
    clean = unescape(clean)
    # Normalize whitespace
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def _extract_link_from_description(description_html: str) -> str:
    """Extract the first href from <a> tag in description HTML."""
    if not description_html:
        return ""
    match = re.search(
        r'<a\s+[^>]*href=["\']([^"\']+)["\']', description_html, re.IGNORECASE
    )
    return match.group(1) if match else ""


def _parse_feedparser_date(published_parsed) -> datetime:
    """Parse feedparser's published_parsed struct_time to timezone-aware datetime."""
    if not published_parsed:
        return None
    try:
        # feedparser returns struct_time in UTC
        dt = datetime(*published_parsed[:6], tzinfo=timezone.utc)
        # Convert to IST
        return dt.astimezone(IST)
    except Exception as e:
        logger.warning(f"Could not parse feedparser date: {published_parsed}, error: {e}")
        return None


def _get_source_from_entry(entry) -> str:
    """Extract source from feedparser entry."""
    # Try source field first
    if hasattr(entry, 'source') and entry.source:
        if hasattr(entry.source, 'title'):
            return entry.source.title
        return str(entry.source)
    # Try to extract from title (Google News format: "Title - Source")
    if hasattr(entry, 'title') and entry.title:
        parts = entry.title.rsplit(" - ", 1)
        if len(parts) == 2:
            return parts[1]
    return ""


RSS_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    )
}

ALLOWED_SOURCE_NEEDLES = (
    "business standard",
    "livemint",
    "live mint",
    "economic times",
    "moneycontrol",
    "money control",
    "ndtv profit",
    "bloomberg",
)
ALLOWED_EXACT_SOURCES = {"mint"}
FUZZY_TITLE_OVERLAP = 0.8

ALLOWED_HOSTS = (
    "business-standard.com",
    "livemint.com",
    "economictimes.indiatimes.com",
    "moneycontrol.com",
    "ndtvprofit.com",
    "bloomberg.com",
    "bloombergquint.com",
)


def clean_sector_query_name(label: str) -> str:
    """Strip '##' suffixes used in overseas sector labels."""
    if not label:
        return ""
    return " ".join(str(label).replace("##", " ").split()).strip()


def week_rss_days_back(week_start) -> int:
    """when:Nd must reach week_start from today, not only the last 7 days."""
    start = datetime.fromisoformat(str(week_start)[:10]).date()
    today = datetime.now(IST).date()
    return max(7, min(21, (today - start).days + 1))


def publisher_allowlisted(source: str) -> bool:
    """
    Keep allowlisted publishers. Empty source is kept until URL resolve (Phase 4).
    """
    if not source or not str(source).strip():
        return True
    text = str(source).strip().lower()
    if text in ALLOWED_EXACT_SOURCES:
        return True
    return any(needle in text for needle in ALLOWED_SOURCE_NEEDLES)


def publisher_host_allowlisted(url: str) -> bool:
    """Keep only allowlisted publisher hosts after Google News URL resolve."""
    if not url:
        return False
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path = (parsed.path or "").lower()
    if host == "ndtv.com" or host.endswith(".ndtv.com"):
        return "profit" in path
    for allowed in ALLOWED_HOSTS:
        if host == allowed or host.endswith("." + allowed):
            return True
    return False


def _title_words(title: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", (title or "").lower()))


def _is_fuzzy_duplicate(title: str, kept_titles: list[str], threshold: float = FUZZY_TITLE_OVERLAP) -> bool:
    words = _title_words(title)
    if not words:
        return False
    for existing in kept_titles:
        other = _title_words(existing)
        if not other:
            continue
        overlap = len(words & other)
        smaller = min(len(words), len(other))
        if smaller and (overlap / smaller) >= threshold:
            return True
    return False


def _parse_rss_entry(entry, news_type: str) -> dict | None:
    pub_dt = _parse_feedparser_date(entry.get("published_parsed"))
    if not pub_dt:
        return None
    title = _clean_html_text(entry.get("title", ""))
    if not title:
        return None
    title = title.rsplit(" - ", 1)[0] if " - " in title else title
    return {
        "title": title,
        "description": _clean_html_text(entry.get("summary", "")),
        "link": entry.get("link", "") or "",
        "source": _get_source_from_entry(entry),
        "published": pub_dt.isoformat(),
        "date": pub_dt.date().isoformat(),
        "pub_date_obj": pub_dt.date(),
        "news_type": news_type,
    }


def _fetch_rss_articles(url: str, news_type: str) -> list[dict]:
    if not url:
        return []
    try:
        response = requests.get(url, timeout=15, headers=RSS_HEADERS)
        response.raise_for_status()
    except requests.RequestException as e:
        logger.error("Failed to fetch RSS from %s: %s", url, e)
        return []
    try:
        feed = feedparser.parse(response.content)
    except Exception as e:
        logger.error("Failed to parse RSS feed from %s: %s", url, e)
        return []
    articles = []
    for entry in feed.entries or []:
        parsed = _parse_rss_entry(entry, news_type)
        if parsed:
            articles.append(parsed)
    return articles


def _queries_for_news_target(target: dict) -> list[tuple[str, str]]:
    """Return (query, news_type) pairs for a Phase 2 news target."""
    name = (target.get("name") or "").strip()
    industry = clean_sector_query_name(target.get("industry") or "")
    target_type = target.get("type") or "stock"
    queries = []
    if target_type == "sector":
        if industry:
            queries.append((f"{INDUSTRY_PREFIX} {industry}", "industry"))
            queries.append((f"{industry} sector India", "industry"))
        return queries
    if name:
        queries.append((name, "instrument"))
    if industry:
        queries.append((f"{INDUSTRY_PREFIX} {industry}", "industry"))
    return queries


def _dedupe_week_articles(articles: list[dict]) -> list[dict]:
    exact = []
    seen = set()
    for article in articles:
        title = article.get("title") or ""
        if not title or title in seen:
            continue
        seen.add(title)
        exact.append(article)

    kept = []
    kept_titles = []
    for article in exact:
        title = article.get("title") or ""
        if _is_fuzzy_duplicate(title, kept_titles):
            continue
        kept.append(article)
        kept_titles.append(title)
    return kept


def fetch_news_for_week(
    target: dict,
    week_start,
    week_end,
) -> list[dict]:
    """
    Harvest Google News RSS for one news target over the official NAV week.
    No LLM scoring. Publisher allowlist applied on RSS source.
    Empty source is kept for later URL-host checks.
    """
    start = datetime.fromisoformat(str(week_start)[:10]).date()
    end = datetime.fromisoformat(str(week_end)[:10]).date()
    days_back = week_rss_days_back(start)
    queries = _queries_for_news_target(target)
    label = target.get("name") or "unknown"
    logger.info(
        "Fetching week news for [%s] %s (%s to %s, when:%sd, %s queries)",
        target.get("type"),
        label,
        start,
        end,
        days_back,
        len(queries),
    )

    raw = []
    for query, news_type in queries:
        url = build_news_url_with_date(query, days_back=days_back)
        logger.info("  RSS query: %s", query)
        raw.extend(_fetch_rss_articles(url, news_type))

    in_week = [
        article
        for article in raw
        if start <= article["pub_date_obj"] <= end
    ]
    allowlisted = [
        article for article in in_week if publisher_allowlisted(article.get("source", ""))
    ]
    selected = _dedupe_week_articles(allowlisted)

    cleaned = []
    for index, article in enumerate(selected, start=1):
        cleaned.append(
            {
                "article_id": index,
                "title": article["title"],
                "description": article.get("description", ""),
                "link": article.get("link", ""),
                "source": article.get("source", ""),
                "published": article.get("published", ""),
                "date": article.get("date", ""),
                "news_type": article.get("news_type", ""),
            }
        )

    logger.info(
        "  %s: raw=%s in-week=%s allowlisted+deduped=%s",
        label,
        len(raw),
        len(in_week),
        len(cleaned),
    )
    return cleaned


def fetch_news_for_dates(
    instrument_name: str,
    industry: str,
    max_per_date: int = 10,
) -> list[dict]:
    """
    Fetch news for instrument and industry from Google News RSS,
    collect up to 10 articles from 2 days ago and 10 articles from 1 day ago (up to 20 total),
    score titles for relevance (0-10) and sentiment (positive/negative) via LLM.

    Returns a list of all enriched scored articles with sentiment and relevancy_score.
    """
    # Calculate target dates in IST
    now_ist = datetime.now(IST)
    two_days_ago = (now_ist - timedelta(days=2)).date()
    one_day_ago = (now_ist - timedelta(days=1)).date()

    logger.info(f"Fetching news for {instrument_name} (industry: {industry})")
    logger.info(f"Target dates: {two_days_ago} (2 days ago), {one_day_ago} (1 day ago)")

    # Build URLs with date filter
    urls = generate_date_filtered_urls_for_holding({
        "instrument_name": instrument_name,
        "industry": industry,
    })

    # Fetch and parse RSS feeds
    all_articles = []

    # Only process URL keys (keys ending with "_news_url")
    url_keys = [k for k in urls.keys() if k.endswith("_news_url")]

    for url_type in url_keys:
        url = urls[url_type]
        if not url:
            continue

        logger.info(f"Fetching {url_type} news from Google News RSS...")
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
        except requests.RequestException as e:
            logger.error(f"Failed to fetch RSS from {url}: {e}")
            continue

        try:
            feed = feedparser.parse(response.content)
        except Exception as e:
            logger.error(f"Failed to parse RSS feed from {url}: {e}")
            continue

        if not feed.entries:
            logger.info(f"No entries found in RSS feed for {url_type}")
            continue

        news_type = "instrument" if "instrument" in url_type else "industry"

        for entry in feed.entries:
            pub_dt = _parse_feedparser_date(entry.get("published_parsed"))
            if not pub_dt:
                continue

            pub_date = pub_dt.date()

            # Only keep articles from target dates (2 days ago and 1 day ago)
            if pub_date not in (two_days_ago, one_day_ago):
                continue

            title = _clean_html_text(entry.get("title", ""))
            if not title:
                continue

            # Remove source suffix from title if present
            title = title.rsplit(" - ", 1)[0] if " - " in title else title

            description = _clean_html_text(entry.get("summary", ""))
            link = entry.get("link", "")
            source = _get_source_from_entry(entry)

            all_articles.append({
                "title": title,
                "description": description,
                "link": link,
                "source": source,
                "published": pub_dt.isoformat(),
                "date": pub_date.isoformat(),
                "pub_date_obj": pub_date,
                "news_type": news_type,
            })

    if not all_articles:
        logger.info("No articles found for target dates")
        return []

    # Deduplicate by title
    seen_titles = set()
    deduped_articles = []
    for article in all_articles:
        title = article.get("title", "")
        if title and title not in seen_titles:
            seen_titles.add(title)
            deduped_articles.append(article)

    # Group by date and take up to max_per_date (10) for 2 days ago and 10 for 1 day ago
    articles_by_date = {two_days_ago: [], one_day_ago: []}
    for article in deduped_articles:
        d = article["pub_date_obj"]
        if d in articles_by_date and len(articles_by_date[d]) < max_per_date:
            articles_by_date[d].append(article)

    selected_articles = (
        articles_by_date[two_days_ago] + articles_by_date[one_day_ago]
    )

    logger.info(
        f"Selected {len(articles_by_date[two_days_ago])} articles from 2 days ago, "
        f"{len(articles_by_date[one_day_ago])} articles from 1 day ago "
        f"(Total: {len(selected_articles)} articles for scoring)"
    )

    if not selected_articles:
        return []

    # Assign article IDs for scoring
    for idx, article in enumerate(selected_articles, start=1):
        article["article_id"] = idx

    # Score all articles for relevance and sentiment using titles only
    logger.info("Scoring news relevance and sentiment via LLM...")
    relevancy_result = score_news_relevance(
        instrument_name=instrument_name,
        industry=industry,
        articles=selected_articles,
    )

    scored_items = relevancy_result.get("scored_news", [])

    # Map score and sentiment by article_id
    score_map = {
        item["article_id"]: {
            "relevancy_score": item.get("relevancy_score", 0),
            "sentiment": item.get("sentiment", "negative"),
        }
        for item in scored_items
    }

    # Enrich original articles
    enriched_articles = []
    for article in selected_articles:
        aid = article["article_id"]
        score_info = score_map.get(
            aid, {"relevancy_score": 0, "sentiment": "negative"}
        )
        enriched_articles.append({
            "title": article["title"],
            "description": article.get("description", ""),
            "link": article.get("link", ""),
            "source": article.get("source", ""),
            "published": article.get("published", ""),
            "date": article.get("date", ""),
            "relevancy_score": score_info["relevancy_score"],
            "sentiment": score_info["sentiment"],
        })

    logger.info(f"Total scored & enriched articles: {len(enriched_articles)}")
    return enriched_articles


def fetch_latest_news(url: str, limit: int = 5, news_type: str = "instrument") -> list[dict]:
    """
    Fetch and parse RSS feed from URL, return latest `limit` news items.
    Each item contains title, description, link, and metadata.
    (Legacy function - kept for backwards compatibility)
    """
    if not url:
        return []

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
    except requests.RequestException as e:
        logger.error(f"Failed to fetch RSS from {url}: {e}")
        return []

    try:
        feed = feedparser.parse(response.content)
    except Exception as e:
        logger.error(f"Failed to parse RSS feed from {url}: {e}")
        return []

    items = []
    for entry in feed.entries:
        pub_dt = _parse_feedparser_date(entry.get('published_parsed'))
        if not pub_dt:
            continue

        title = _clean_html_text(entry.get('title', ''))
        if not title:
            continue

        title = title.rsplit(" - ", 1)[0] if " - " in title else title
        description = _clean_html_text(entry.get('summary', ''))
        link = entry.get('link', '')
        source = _get_source_from_entry(entry)

        items.append({
            "title": title,
            "description": description,
            "link": link,
            "source": source,
            "_pub_date": pub_dt,
        })

    # Sort by pubDate descending (newest first)
    items.sort(key=lambda x: x["_pub_date"], reverse=True)

    # Take top `limit` items
    result = [
        {
            "title": item["title"],
            "description": item["description"],
            "link": item["link"],
            "source": item["source"],
            "news_type": news_type,
        }
        for item in items[:limit]
    ]

    return result


def fetch_news_for_urls(urls: dict) -> dict:
    """
    Fetch latest news for both instrument and industry URLs.
    Returns a dict with keys matching the URL types.
    (Legacy function - kept for backwards compatibility)
    """
    result = {}

    instrument_url = urls.get("instrument_news_url")
    if instrument_url:
        instrument_name = urls.get("instrument_name", "instrument")
        logger.info(f"Fetching news for instrument: {instrument_name}")
        result[instrument_name] = fetch_latest_news(instrument_url, news_type="instrument")

    industry_url = urls.get("industry_news_url")
    if industry_url:
        industry = urls.get("industry", "industry")
        logger.info(f"Fetching news for industry: {industry}")
        result[f"Indian {industry}"] = fetch_latest_news(industry_url, news_type="industry")

    return result


def process_instrument_lookup(data: dict, name: str):
    """
    Given the full JSON data and a user-entered instrument name:
      - not found            -> print a not-found message
      - found, industry null -> print "can't create urls"
      - found, industry set  -> build URLs and fetch latest news
    """
    top_holdings = data.get("data", {}).get("top_holdings", [])
    holding = find_holding(top_holdings, name)

    if holding is None:
        print(f"\n'{name}' was not found in top_holdings.")
        return

    industry = holding.get("industry")
    if not industry or industry.strip() == "null":
        print(
            f"\nFound '{holding['instrument_name']}', but industry is null — can't create urls."
        )
        return

    urls = generate_urls_for_holding(holding)
    print(f"\nFound '{holding['instrument_name']}' (industry: {industry})")
    print(json.dumps(urls, indent=2))

    print("\nFetching latest news...")
    news = fetch_news_for_urls(urls)
    print(json.dumps(news, indent=2))

    # Collect all news items from both instrument and industry sources
    all_items = []
    for source, articles in news.items():
        for article in articles:
            all_items.append(article)

    # Deduplicate by title (keep first occurrence with its original link)
    seen_titles = set()
    deduped_items = []
    for item in all_items:
        title = item.get("title", "")
        if title and title not in seen_titles:
            seen_titles.add(title)
            deduped_items.append(item)

    # Assign stable article_ids
    for idx, item in enumerate(deduped_items, start=1):
        item["article_id"] = idx

    # Take max 5 instrument + 5 industry = 10 total
    instrument_items = [item for item in deduped_items if item.get("news_type") == "instrument"][:5]
    industry_items = [item for item in deduped_items if item.get("news_type") == "industry"][:5]
    combined_items = instrument_items + industry_items

    logger.info(f"Fetched {len(instrument_items)} instrument articles, {len(industry_items)} industry articles")
    logger.info(f"Combined {len(combined_items)} articles for scoring")

    if combined_items:
        print("\nScoring news relevance...")
        instrument_name = holding["instrument_name"]
        relevancy_result = score_news_relevance(
            instrument_name=instrument_name,
            industry=industry,
            articles=combined_items,
        )
        print(json.dumps(relevancy_result, indent=2))


if __name__ == "__main__":
    # Swap SAMPLE_DATA for your real JSON, e.g.:
    # with open("your_file.json") as f:
    #     data = json.load(f)
    data = SAMPLE_DATA

    instrument_name = input("Enter instrument name: ")
    process_instrument_lookup(data, instrument_name)