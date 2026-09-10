import threading
import time

from curl_cffi import requests

DEFAULT_TIMEOUT = 20
GOOGLE_COOKIES = {"CONSENT": "YES+"}
RETRY_STATUSES = {401, 403, 408, 425, 429, 500, 502, 503, 504}
_RETRY_IMPERSONATE = ("safari", "firefox135", "chrome131")
_local = threading.local()


def make_session(impersonate="chrome"):
    session = requests.Session(impersonate=impersonate)
    session.cookies.update(GOOGLE_COOKIES)
    return session


def thread_session():
    session = getattr(_local, "session", None)
    if session is None:
        session = make_session()
        _local.session = session
    return session


def fetch_url(session, url, timeout=DEFAULT_TIMEOUT, referer=None, retries=2):
    """GET a URL. Returns (final_url, html, error)."""
    last_error = None
    current = session
    for attempt in range(retries + 1):
        if attempt > 0:
            current = make_session(_RETRY_IMPERSONATE[(attempt - 1) % len(_RETRY_IMPERSONATE)])
        headers = {"Referer": referer} if referer else None
        try:
            response = current.get(
                url,
                timeout=timeout,
                allow_redirects=True,
                headers=headers,
            )
            if response.status_code >= 400:
                last_error = f"{response.status_code} {response.reason} for url: {url}"
                if response.status_code in RETRY_STATUSES and attempt < retries:
                    _backoff(attempt)
                    continue
                return None, None, last_error
            text = response.text or ""
            if not text.strip():
                last_error = "empty page"
                if attempt < retries:
                    _backoff(attempt)
                    continue
                return response.url, None, last_error
            return response.url, text, None
        except requests.RequestsError as exc:
            last_error = str(exc)
        except Exception as exc:
            last_error = str(exc)
        if attempt < retries:
            _backoff(attempt)
    return None, None, last_error


def _backoff(attempt):
    time.sleep(0.4 * (2 ** attempt))
