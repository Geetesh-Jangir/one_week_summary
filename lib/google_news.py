"""Resolve Google News article wrappers and collect links from RSS feeds."""

import json
import re
import time
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

from lib.fetch import fetch_url

BATCH_EXECUTE_URL = "https://news.google.com/_/DotsSplashUi/data/batchexecute"
_GOOGLE_HOSTS = {"news.google.com", "www.news.google.com"}
_SIGNATURE_RE = re.compile(r'data-n-a-sg="([^"]+)"')
_TIMESTAMP_RE = re.compile(r'data-n-a-ts="([^"]+)"')
_GARTURL_RE = re.compile(r'garturlres","(https?://[^"\\]+)"')

_REQUEST_SHELL = [
    ["X", "X", ["X", "X"], None, None, 1, 1, "US:en", None, 1, None, None, None, None, None, 0, 1],
    "X",
    "X",
    1,
    [1, 1, 1],
    1,
    1,
    None,
    0,
    0,
    None,
    0,
]


def is_google_news_article_url(url):
    parsed = urlparse(url)
    if parsed.netloc.lower() not in _GOOGLE_HOSTS:
        return False
    parts = [part for part in parsed.path.split("/") if part]
    return len(parts) >= 2 and parts[-2] in {"articles", "read"}


def article_id_from_url(url):
    return url.rstrip("/").split("/")[-1].split("?")[0]


def resolve_google_news_url(session, url, timeout=20, retries=2):
    """Turn a news.google.com/rss/articles/CBMi… URL into the publisher URL."""
    if not is_google_news_article_url(url):
        return url, None

    article_id = article_id_from_url(url)
    last_error = None
    for attempt in range(retries + 1):
        _page_url, html, error = fetch_url(session, url, timeout=timeout, retries=0)
        if error or not html:
            last_error = error or "empty Google News page"
        else:
            sig_match = _SIGNATURE_RE.search(html)
            ts_match = _TIMESTAMP_RE.search(html)
            if not sig_match or not ts_match or not ts_match.group(1).isdigit():
                last_error = "no signature/timestamp on Google News page"
            else:
                resolved, last_error = _batchexecute(
                    session,
                    article_id,
                    int(ts_match.group(1)),
                    sig_match.group(1),
                    timeout,
                )
                if resolved:
                    return resolved, None
        if attempt < retries:
            time.sleep(0.5 * (2 ** attempt))
    return None, last_error or "could not resolve Google News URL"


def _batchexecute(session, article_id, timestamp, signature, timeout):
    rpc_inner = json.dumps(
        ["garturlreq", _REQUEST_SHELL, article_id, timestamp, signature],
        separators=(",", ":"),
    )
    f_req = json.dumps([[["Fbv4je", rpc_inner, None, "generic"]]], separators=(",", ":"))
    try:
        response = session.post(
            BATCH_EXECUTE_URL,
            data={"f.req": f_req},
            headers={
                "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                "Referer": "https://news.google.com/",
            },
            timeout=timeout,
        )
        if response.status_code >= 400:
            return None, f"batchexecute {response.status_code}"
        resolved = _parse_garturlres(response.text)
        if not resolved:
            return None, "no garturlres in batchexecute response"
        return resolved, None
    except Exception as exc:
        return None, f"batchexecute failed: {exc}"


def _parse_garturlres(body):
    if body.startswith(")]}'"):
        body = body.split("\n", 1)[1]
    body = body.lstrip()
    head, _, tail = body.partition("\n")
    if head.strip().isdigit():
        body = tail
    try:
        envelopes = json.loads(body)
    except json.JSONDecodeError:
        match = _GARTURL_RE.search(body)
        return match.group(1) if match else None
    for env in envelopes:
        if not (isinstance(env, list) and len(env) >= 3):
            continue
        if env[0] != "wrb.fr" or env[1] != "Fbv4je":
            continue
        try:
            payload = json.loads(env[2])
        except (TypeError, json.JSONDecodeError):
            continue
        if (
            isinstance(payload, list)
            and len(payload) >= 2
            and payload[0] == "garturlres"
            and isinstance(payload[1], str)
            and payload[1].startswith("http")
        ):
            return payload[1]
    match = _GARTURL_RE.search(body)
    return match.group(1) if match else None


def parse_rss_links(xml_text):
    """Return item <link> values from an RSS 2.0 / Atom feed."""
    root = ET.fromstring(xml_text.lstrip("\ufeff"))
    links = []
    for item in root.iter():
        tag = item.tag.split("}")[-1]
        if tag not in {"item", "entry"}:
            continue
        for child in item:
            child_tag = child.tag.split("}")[-1]
            if child_tag != "link":
                continue
            link = (child.get("href") or child.text or "").strip()
            if link:
                links.append(link)
            break
    return links
