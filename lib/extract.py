"""Generic article extraction. One trafilatura pass; BeautifulSoup only if thin."""

import re
from urllib.parse import urljoin, urlparse

from lxml.etree import tostring
from trafilatura import extract_with_metadata
from bs4 import BeautifulSoup

THIN_TEXT_CHARS = 120
_IMG_RE = re.compile(r"""<img[^>]+(?:src|data-src)=["']([^"']+)""", re.I)


def extract_article(html, url):
    doc = None
    try:
        doc = extract_with_metadata(
            html,
            url=url,
            include_comments=False,
            include_tables=True,
            include_images=True,
            include_links=True,
            favor_recall=True,
            output_format="txt",
        )
    except Exception:
        doc = None

    text = ""
    content_html = ""
    title = None
    authors = []
    date = None
    sitename = None
    og_image = None

    if doc is not None:
        text = (doc.raw_text or doc.text or "").strip()
        if doc.body is not None:
            try:
                content_html = tostring(doc.body, encoding="unicode", method="html")
            except Exception:
                content_html = ""
        title = _clean(doc.title)
        authors = _authors(doc.author)
        date = _clean(doc.date)
        sitename = _clean(doc.sitename) or urlparse(url).netloc
        og_image = _clean(doc.image)

    if len(text) < THIN_TEXT_CHARS:
        fallback = _meta_fallback(html, url)
        title = title or fallback["title"]
        authors = authors or fallback["authors"]
        date = date or fallback["date"]
        sitename = sitename or fallback["sitename"] or urlparse(url).netloc
        og_image = og_image or fallback["og_image"]
        if len((fallback["text"] or "")) > len(text):
            text = fallback["text"]
        if not content_html:
            content_html = fallback["content_html"]

    images = _collect_images(content_html, url, og_image)
    return {
        "title": title,
        "authors": authors,
        "date": date,
        "sitename": sitename,
        "text": text or "",
        "content_html": content_html or "",
        "images": images,
        "thin": len((text or "").strip()) < THIN_TEXT_CHARS,
    }


def _meta_fallback(html, url):
    soup = BeautifulSoup(html, "lxml")
    title = _meta(soup, property="og:title") or _meta(soup, name="twitter:title")
    if not title and soup.title and soup.title.string:
        title = soup.title.string.strip()
    article = soup.find("article")
    text = article.get_text("\n", strip=True) if article else (
        _meta(soup, property="og:description") or _meta(soup, name="description") or ""
    )
    return {
        "title": title,
        "authors": _authors(_meta(soup, name="author") or _meta(soup, property="author")),
        "date": _meta(soup, property="article:published_time") or _meta(soup, name="date"),
        "sitename": _meta(soup, property="og:site_name"),
        "og_image": _meta(soup, property="og:image"),
        "text": text,
        "content_html": str(article) if article else "",
    }


def _collect_images(content_html, page_url, og_image):
    seen = set()
    images = []

    def add(src):
        if not src:
            return
        absolute = urljoin(page_url, src.strip())
        if absolute in seen or not absolute.startswith("http"):
            return
        seen.add(absolute)
        images.append(absolute)

    add(og_image)
    for src in _IMG_RE.findall(content_html or ""):
        add(src)
    return images


def _authors(raw):
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    return [part.strip() for part in re.split(r"[;|]| and ", str(raw)) if part.strip()]


def _clean(value):
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _meta(soup, property=None, name=None):
    attrs = {"property": property} if property else {"name": name}
    tag = soup.find("meta", attrs=attrs)
    if tag and tag.get("content"):
        return tag["content"].strip()
    return None
