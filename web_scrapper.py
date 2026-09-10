#!/usr/bin/env python3
"""Scrape publisher pages from Google News article URLs or RSS feeds."""

import argparse
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from lib.extract import extract_article
from lib.fetch import fetch_url, make_session, thread_session
from lib.google_news import (
    is_google_news_article_url,
    parse_rss_links,
    resolve_google_news_url,
)

INDIA_FEEDS = [
    "https://news.google.com/rss?hl=en-IN&gl=IN&ceid=IN:en",
    "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=en-IN&gl=IN&ceid=IN:en",
    "https://news.google.com/rss/headlines/section/topic/NATION?hl=en-IN&gl=IN&ceid=IN:en",
    "https://news.google.com/rss/headlines/section/topic/TECHNOLOGY?hl=en-IN&gl=IN&ceid=IN:en",
    "https://news.google.com/rss/headlines/section/topic/WORLD?hl=en-IN&gl=IN&ceid=IN:en",
    "https://news.google.com/rss/search?q=mutual%20funds&hl=en-IN&gl=IN&ceid=IN:en",
    "https://news.google.com/rss/search?q=stock%20market&hl=en-IN&gl=IN&ceid=IN:en",
    "https://news.google.com/rss/search?q=Sensex%20OR%20Nifty&hl=en-IN&gl=IN&ceid=IN:en",
    "https://news.google.com/rss/search?q=RBI%20OR%20SEBI&hl=en-IN&gl=IN&ceid=IN:en",
    "https://news.google.com/rss/search?q=IPO&hl=en-IN&gl=IN&ceid=IN:en",
]


def main():
    parser = argparse.ArgumentParser(
        description="Resolve Google News wrappers and extract article content from any publisher."
    )
    parser.add_argument("urls", nargs="*", help="Google News or direct article URLs")
    parser.add_argument("--file", "-f", help="Text file with one URL per line")
    parser.add_argument(
        "--rss", action="append", default=[], help="RSS feed URL (repeatable)"
    )
    parser.add_argument(
        "--preset",
        choices=["india"],
        help="Built-in Google News RSS set (india = top + business + markets)",
    )
    parser.add_argument("--limit", type=int, help="Cap number of URLs after collection")
    parser.add_argument("--save-urls", help="Write collected URLs to this file")
    parser.add_argument("--out", default="out", help="Output directory (default: out)")
    parser.add_argument(
        "--workers", type=int, default=8, help="Parallel workers (default: 8)"
    )
    parser.add_argument(
        "--retries", type=int, default=2, help="Retries per request (default: 2)"
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0,
        help="Optional pause after each article (default: 0)",
    )
    parser.add_argument(
        "--no-html", action="store_true", help="JSON only, skip raw HTML files"
    )
    args = parser.parse_args()

    session = make_session()
    input_urls = _collect_input_urls(session, args)
    if args.save_urls:
        save_path = Path(args.save_urls)
        if not save_path.is_absolute():
            save_path = ROOT / save_path
        save_path.write_text("\n".join(input_urls) + "\n", encoding="utf-8")
        print(f"Saved {len(input_urls)} URLs to {save_path}")
    if not input_urls:
        parser.error("Pass URLs, --file, --rss, or --preset")

    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    total = len(input_urls)
    workers = max(1, args.workers)
    results = [None] * total
    done = 0

    def job(index_url):
        index, input_url = index_url
        try:
            record = scrape_one(thread_session(), input_url, retries=args.retries)
            if args.delay:
                time.sleep(args.delay)
            saved = _write_record(out_dir, index, record, save_html=not args.no_html)
            return index, record, saved
        except Exception as exc:
            record = {
                "input_url": input_url,
                "resolved_url": None,
                "final_url": None,
                "title": None,
                "authors": [],
                "date": None,
                "sitename": None,
                "text": "",
                "content_html": "",
                "images": [],
                "status": "fetch_failed",
                "error": str(exc),
                "fetched_at": _now_iso(),
            }
            return index, record, (None, None)

    print(f"Scraping {total} URL(s) with {workers} worker(s)...")
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [
            pool.submit(job, (i, url)) for i, url in enumerate(input_urls, start=1)
        ]
        for future in as_completed(futures):
            index, record, saved = future.result()
            results[index - 1] = record
            done += 1
            _print_progress(done, total, record, saved)

    summary_path = out_dir / "summary.json"
    counts = _status_counts(results)
    summary_path.write_text(
        json.dumps(
            {
                "fetched_at": _now_iso(),
                "count": total,
                "workers": workers,
                **counts,
                "results": [_summary_row(item) for item in results],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nWrote {total} article(s) to {out_dir}")
    print(
        "Status: "
        + ", ".join(
            f"{key}={value}" for key, value in counts.items() if key != "scraped"
        )
        + f" | scraped={counts['scraped']}/{total}"
    )
    print(f"Summary: {summary_path}")
    if counts["scraped"] < total:
        sys.exit(1)


def scrape_one(session, input_url, retries=2):
    record = {
        "input_url": input_url,
        "resolved_url": None,
        "final_url": None,
        "title": None,
        "authors": [],
        "date": None,
        "sitename": None,
        "text": "",
        "content_html": "",
        "images": [],
        "status": "ok",
        "error": None,
        "fetched_at": _now_iso(),
    }

    resolved_url = input_url
    if is_google_news_article_url(input_url):
        resolved_url, error = resolve_google_news_url(
            session, input_url, retries=retries
        )
        if error or not resolved_url:
            record["status"] = "resolve_failed"
            record["error"] = error or "could not resolve Google News URL"
            return record

    record["resolved_url"] = resolved_url
    referer = (
        input_url
        if is_google_news_article_url(input_url)
        else "https://news.google.com/"
    )
    final_url, html, error = fetch_url(
        session, resolved_url, referer=referer, retries=retries
    )
    if error or not html:
        record["status"] = "fetch_failed"
        record["error"] = error or "empty publisher page"
        return record

    record["final_url"] = final_url or resolved_url
    extracted = extract_article(html, record["final_url"])
    record.update(
        {
            "title": extracted["title"],
            "authors": extracted["authors"],
            "date": extracted["date"],
            "sitename": extracted["sitename"],
            "text": extracted["text"],
            "content_html": extracted["content_html"],
            "images": extracted["images"],
        }
    )
    record["_raw_html"] = html
    if extracted["thin"]:
        record["status"] = "extract_thin"
        record["error"] = (
            "extracted text is short; page may be JS-rendered or paywalled"
        )
    return record


def _collect_input_urls(session, args):
    urls = list(args.urls or [])
    feeds = list(args.rss or [])
    if args.preset == "india":
        feeds.extend(INDIA_FEEDS)

    if args.file:
        file_path = Path(args.file)
        if not file_path.is_absolute():
            file_path = ROOT / file_path
        for line in file_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                urls.append(line)

    for feed in feeds:
        _final, xml_text, error = fetch_url(session, feed, retries=2)
        if error or not xml_text:
            print(f"warn: RSS failed ({feed}): {error or 'empty'}", file=sys.stderr)
            continue
        links = parse_rss_links(xml_text)
        if not links:
            print(f"warn: RSS had no links ({feed})", file=sys.stderr)
            continue
        urls.extend(links)

    unique = []
    seen = set()
    for url in urls:
        if url not in seen:
            seen.add(url)
            unique.append(url)
    if args.limit:
        unique = unique[: args.limit]
    return unique


def _status_counts(results):
    counts = {"ok": 0, "extract_thin": 0, "fetch_failed": 0, "resolve_failed": 0}
    for item in results:
        status = item["status"]
        counts[status] = counts.get(status, 0) + 1
    counts["scraped"] = counts["ok"] + counts["extract_thin"]
    return counts


def _summary_row(record):
    return {
        "input_url": record.get("input_url"),
        "resolved_url": record.get("resolved_url"),
        "final_url": record.get("final_url"),
        "title": record.get("title"),
        "sitename": record.get("sitename"),
        "status": record.get("status"),
        "error": record.get("error"),
        "text_chars": len(record.get("text") or ""),
    }


def _write_record(out_dir, index, record, save_html):
    slug = _slug(record.get("title") or record.get("final_url") or record["input_url"])
    stem = f"{index:03d}_{slug}"
    payload = {key: value for key, value in record.items() if not key.startswith("_")}
    json_path = out_dir / f"{stem}.json"
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    html_path = None
    if save_html and record.get("_raw_html"):
        html_path = out_dir / f"{stem}.html"
        html_path.write_text(record["_raw_html"], encoding="utf-8")
    return json_path, html_path


def _print_progress(done, total, record, saved):
    label = record.get("title") or record.get("final_url") or record["input_url"]
    label = str(label).encode("ascii", "replace").decode("ascii")
    if len(label) > 90:
        label = label[:87] + "..."
    print(f"[{done}/{total}] {record['status']}: {label}")
    if record.get("error"):
        print(f"    error: {record['error']}")


def _slug(value):
    text = str(value or "")
    parsed = urlparse(text)
    if parsed.scheme:
        text = parsed.netloc + parsed.path
    text = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return (text[:80] or "article").rstrip("-")


def _now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    main()
