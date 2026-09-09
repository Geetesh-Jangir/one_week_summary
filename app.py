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
from datetime import datetime
from html import unescape
from urllib.parse import quote_plus
from xml.etree import ElementTree

import requests

from news_relevancy_agent import score_news_relevance

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_URL = "https://news.google.com/rss/search"

# Prefixed onto the industry text before building its query,
# e.g. "Banks" -> "Indian Banks"
INDUSTRY_PREFIX = "Indian"

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


def _parse_pub_date(pub_date_str: str) -> datetime:
    """Parse RFC 822 / RFC 2822 date string to datetime."""
    if not pub_date_str:
        return datetime.min
    # Try common RSS date formats
    formats = [
        "%a, %d %b %Y %H:%M:%S %Z",  # Tue, 08 Sep 2026 06:55:52 GMT
        "%a, %d %b %Y %H:%M:%S %z",  # Tue, 08 Sep 2026 06:55:52 +0000
        "%Y-%m-%dT%H:%M:%S%z",  # ISO 8601
        "%Y-%m-%dT%H:%M:%SZ",  # ISO 8601 UTC
    ]
    for fmt in formats:
        try:
            return datetime.strptime(pub_date_str.strip(), fmt)
        except ValueError:
            continue
    logger.warning(f"Could not parse date: {pub_date_str}")
    return datetime.min


def fetch_latest_news(url: str, limit: int = 5, news_type: str = "instrument") -> list[dict]:
    """
    Fetch and parse RSS feed from URL, return latest `limit` news items.
    Each item contains title, description, link, and metadata.
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
        root = ElementTree.fromstring(response.content)
    except ElementTree.ParseError as e:
        logger.error(f"Failed to parse XML from {url}: {e}")
        return []

    items = []
    for item in root.findall(".//channel/item"):
        title_elem = item.find("title")
        description_elem = item.find("description")
        pub_date_elem = item.find("pubDate")

        title = (
            _clean_html_text(title_elem.text)
            if title_elem is not None and title_elem.text
            else ""
        )
        description_html = description_elem.text if description_elem is not None else ""
        description = _clean_html_text(description_html)
        link = _extract_link_from_description(description_html)
        pub_date = (
            _parse_pub_date(pub_date_elem.text)
            if pub_date_elem is not None and pub_date_elem.text
            else datetime.min
        )

        if title:  # Only include items with a title
            items.append(
                {
                    "title": title.rsplit(" - ", 1)[0],
                    "description": description,
                    "link": link,
                    "_pub_date": pub_date,  # Used for sorting, not in final output
                }
            )

    # Sort by pubDate descending (newest first)
    items.sort(key=lambda x: x["_pub_date"], reverse=True)

    # Take top `limit` items and remove the internal _pub_date field
    result = [
        {
            "title": item["title"],
            "description": item["description"],
            "link": item["link"],
            "news_type": news_type,
        }
        for item in items[:limit]
    ]

    return result


def fetch_news_for_urls(urls: dict) -> dict:
    """
    Fetch latest news for both instrument and industry URLs.
    Returns a dict with keys matching the URL types.
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
