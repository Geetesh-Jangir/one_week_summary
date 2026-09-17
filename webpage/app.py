"""Local fund-desk UI: list funds, run the pipeline, show NAV + summary."""

from __future__ import annotations

import json
import sys
import threading
from collections import deque
from pathlib import Path
from subprocess import PIPE, Popen

from flask import Flask, jsonify, request, send_from_directory

WEBPAGE_DIR = Path(__file__).resolve().parent
ROOT = WEBPAGE_DIR.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fund_data import (  # noqa: E402
    HOLDINGS_NAME,
    NAV_HISTORY_NAME,
    SECTOR_NAME,
    identity_for_fund,
    listed_fund_ids,
    load_holdings,
    load_nav_history,
    load_sectors,
    parse_nav_percentage,
    resolve_fund_data_dir,
)
from rupeestop_fund import FundFetchError, fetch_latest_nav_date, normalize_isin, sync_fund  # noqa: E402

STATIC_DIR = WEBPAGE_DIR / "static"
OUTPUT_SCRAPPER_DIR = ROOT / "output-scrapper"
LOG_TAIL_LIMIT = 40

app = Flask(__name__, static_folder=None)

_job_lock = threading.Lock()
_job = {
    "status": "idle",
    "fund_id": None,
    "error": None,
    "log": deque(maxlen=LOG_TAIL_LIMIT),
    "process": None,
}


def display_name(fund_id: str) -> str:
    return identity_for_fund(fund_id)["fund_name"]


def known_fund(fund_id: str) -> bool:
    try:
        resolve_fund_data_dir(fund_id)
        return True
    except FileNotFoundError:
        return False


def saved_nav_date(fund_id: str) -> str | None:
    path = OUTPUT_SCRAPPER_DIR / fund_id / "result.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    nav_date = str(data.get("nav_date") or "").strip()[:10]
    return nav_date or None


def has_cached_summary(fund_id: str, latest_nav_date: str) -> bool:
    summary = read_summary(fund_id)
    if not summary.get("found") or summary.get("empty"):
        return False
    stored = summary.get("nav_date") or saved_nav_date(fund_id)
    return bool(stored) and stored == latest_nav_date


def _clean_label(value) -> str:
    return " ".join(str(value or "").replace("##", " ").replace("£", "").split())


def top_book(fund_id: str) -> dict:
    data_dir = resolve_fund_data_dir(fund_id)
    holdings = load_holdings(data_dir / HOLDINGS_NAME)
    ranked_holdings = sorted(
        holdings,
        key=lambda row: parse_nav_percentage(row.get("percentage", 0)),
        reverse=True,
    )[:5]
    sectors = load_sectors(data_dir / SECTOR_NAME)
    ranked_sectors = sorted(
        sectors,
        key=lambda row: row.get("percentage") or 0,
        reverse=True,
    )[:5]
    identity = identity_for_fund(fund_id, data_dir)
    return {
        "fund_id": fund_id,
        **identity,
        "holdings": [
            {
                "name": _clean_label(row.get("instrument_name") or row.get("name")),
                "industry": _clean_label(row.get("industry") or row.get("detail")),
                "percentage": round(parse_nav_percentage(row.get("percentage", 0)), 2),
            }
            for row in ranked_holdings
        ],
        "sectors": [
            {
                "name": _clean_label(row.get("sector")),
                "percentage": round(float(row.get("percentage") or 0), 2),
            }
            for row in ranked_sectors
        ],
    }


def last_seven_nav(fund_id: str) -> dict:
    rows = load_nav_history(resolve_fund_data_dir(fund_id) / NAV_HISTORY_NAME)
    rows = sorted(rows, key=lambda row: row["nav_date"])[-7:]
    dates = [str(row["nav_date"])[:10] for row in rows]
    values = [round(float(row["nav_value"]), 4) for row in rows]
    change_pct = None
    if len(values) >= 2 and values[0] != 0:
        change_pct = round((values[-1] - values[0]) / values[0] * 100, 3)
    identity = identity_for_fund(fund_id)
    return {
        "fund_id": fund_id,
        **identity,
        "name": identity["fund_name"],
        "dates": dates,
        "values": values,
        "start_nav": values[0] if values else None,
        "end_nav": values[-1] if values else None,
        "change_pct": change_pct,
    }


def read_summary(fund_id: str) -> dict:
    path = OUTPUT_SCRAPPER_DIR / fund_id / "result.json"
    if not path.exists():
        return {"fund_id": fund_id, "investor_summary": "", "important_news": [], "found": False, "empty": False}
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return {"fund_id": fund_id, "investor_summary": "", "important_news": [], "found": True, "empty": True}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {"fund_id": fund_id, "investor_summary": raw, "important_news": [], "found": True, "empty": False}
    text = str(data.get("investor_summary") or "").strip()
    news = data.get("important_news")
    if not isinstance(news, list):
        news = []
    important_news = []
    for item in news:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        url = str(item.get("url") or item.get("resolved_url") or item.get("link") or "").strip()
        if not title or not url:
            continue
        important_news.append(
            {
                "title": title,
                "url": url,
                "source": str(item.get("source") or "").strip(),
            }
        )
    nav_date = str(data.get("nav_date") or "").strip()[:10]
    return {
        "fund_id": fund_id,
        "investor_summary": text,
        "important_news": important_news,
        "isin": str(data.get("isin") or fund_id),
        "nav_date": nav_date or None,
        "found": True,
        "empty": not bool(text),
    }


def _append_log(line: str) -> None:
    text = (line or "").rstrip()
    if text:
        _job["log"].append(text)


def _stream_pipe(pipe) -> None:
    if pipe is None:
        return
    for line in iter(pipe.readline, ""):
        _append_log(line)
    pipe.close()


def _wait_for_job(process: Popen, fund_id: str) -> None:
    stdout_thread = threading.Thread(target=_stream_pipe, args=(process.stdout,), daemon=True)
    stderr_thread = threading.Thread(target=_stream_pipe, args=(process.stderr,), daemon=True)
    stdout_thread.start()
    stderr_thread.start()
    code = process.wait()
    stdout_thread.join(timeout=2)
    stderr_thread.join(timeout=2)
    with _job_lock:
        _job["process"] = None
        if _job["fund_id"] != fund_id:
            return
        if code == 0:
            _job["status"] = "done"
            _job["error"] = None
            _append_log("Pipeline finished.")
        else:
            _job["status"] = "error"
            _job["error"] = f"Pipeline exited with code {code}"
            _append_log(_job["error"])


@app.get("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.get("/styles.css")
def styles_css():
    return send_from_directory(STATIC_DIR, "styles.css")


@app.get("/app.js")
def app_js():
    return send_from_directory(STATIC_DIR, "app.js")


@app.get("/static/<path:filename>")
def static_files(filename):
    return send_from_directory(STATIC_DIR, filename)


@app.get("/data/<fund_id>.json")
def fund_book_file(fund_id: str):
    if not known_fund(fund_id):
        return jsonify({"error": "Unknown fund"}), 404
    try:
        payload = top_book(fund_id)
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    payload["important_news"] = read_summary(fund_id).get("important_news") or []
    return jsonify(payload)


@app.get("/api/funds")
def api_funds():
    funds = []
    for fund_id in listed_fund_ids():
        identity = identity_for_fund(fund_id)
        funds.append(
            {
                "id": fund_id,
                "name": identity["fund_name"],
                "subtitle": identity["subtitle"],
                "isin": identity["isin"],
            }
        )
    return jsonify({"funds": funds})


@app.post("/api/lookup")
def api_lookup():
    payload = request.get_json(silent=True) or {}
    raw = payload.get("isin") or payload.get("fund_id") or ""
    try:
        isin = normalize_isin(raw)
        sync = sync_fund(isin)
        latest = sync.get("nav_end") or fetch_latest_nav_date(isin)
        book = top_book(isin)
        nav = last_seven_nav(isin)
        summary = read_summary(isin)
        cached = has_cached_summary(isin, latest)
        return jsonify(
            {
                "fund_id": isin,
                "isin": isin,
                "fund_name": book.get("fund_name") or nav.get("fund_name"),
                "plan": book.get("plan") or "",
                "option": book.get("option") or "",
                "plan_label": book.get("plan_label") or "",
                "option_label": book.get("option_label") or "",
                "subtitle": book.get("subtitle") or "",
                "holdings": book.get("holdings") or [],
                "sectors": book.get("sectors") or [],
                "dates": nav.get("dates") or [],
                "values": nav.get("values") or [],
                "start_nav": nav.get("start_nav"),
                "end_nav": nav.get("end_nav"),
                "change_pct": nav.get("change_pct"),
                "latest_nav_date": latest,
                "nav_stale": bool(summary.get("found") and not cached),
                "cached": cached,
                "investor_summary": summary.get("investor_summary") or "",
                "important_news": summary.get("important_news") or [],
                "summary_nav_date": summary.get("nav_date"),
            }
        )
    except FundFetchError as exc:
        return jsonify({"error": str(exc)}), 400
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404


@app.get("/api/book/<fund_id>")
def api_book(fund_id: str):
    if not known_fund(fund_id):
        return jsonify({"error": "Unknown fund"}), 404
    try:
        return jsonify(top_book(fund_id))
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404


@app.get("/api/nav/<fund_id>")
def api_nav(fund_id: str):
    if not known_fund(fund_id):
        return jsonify({"error": "Unknown fund"}), 404
    try:
        payload = last_seven_nav(fund_id)
        payload.update(top_book(fund_id))
        return jsonify(payload)
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404


@app.get("/api/summary/<fund_id>")
def api_summary(fund_id: str):
    path = OUTPUT_SCRAPPER_DIR / fund_id / "result.json"
    if not path.exists() and not known_fund(fund_id):
        return jsonify({"error": "Unknown fund"}), 404
    return jsonify(read_summary(fund_id))


@app.get("/api/run/status")
def api_run_status():
    with _job_lock:
        return jsonify(
            {
                "status": _job["status"],
                "fund_id": _job["fund_id"],
                "error": _job["error"],
                "log_tail": list(_job["log"])[-12:],
            }
        )


def _start_pipeline(fund_id: str):
    with _job_lock:
        if _job["status"] == "running":
            return (
                jsonify(
                    {
                        "error": "A run is already in progress",
                        "fund_id": _job["fund_id"],
                        "status": "running",
                    }
                ),
                409,
            )
        _job["status"] = "running"
        _job["fund_id"] = fund_id
        _job["error"] = None
        _job["log"].clear()
        _append_log(f"Starting {display_name(fund_id)}…")
        process = Popen(
            [sys.executable, str(ROOT / "main.py"), "--isin", fund_id],
            cwd=str(ROOT),
            stdout=PIPE,
            stderr=PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        _job["process"] = process
    threading.Thread(target=_wait_for_job, args=(process, fund_id), daemon=True).start()
    return jsonify({"status": "running", "fund_id": fund_id})


@app.post("/api/run")
@app.post("/api/run/<fund_id>")
def api_run(fund_id: str | None = None):
    payload = request.get_json(silent=True) or {}
    raw = fund_id or payload.get("isin") or payload.get("fund_id") or ""
    try:
        isin = normalize_isin(raw)
        latest = fetch_latest_nav_date(isin)
        if has_cached_summary(isin, latest):
            identity = identity_for_fund(isin)
            return jsonify(
                {
                    "status": "cached",
                    "fund_id": isin,
                    "isin": isin,
                    "nav_date": latest,
                    "fund_name": identity["fund_name"],
                    "subtitle": identity["subtitle"],
                }
            )
        sync_fund(isin)
        return _start_pipeline(isin)
    except FundFetchError as exc:
        return jsonify({"error": str(exc)}), 400
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404


if __name__ == "__main__":
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    app.run(host="127.0.0.1", port=5000, debug=False)
