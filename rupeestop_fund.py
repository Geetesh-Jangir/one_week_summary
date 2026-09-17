"""Fetch fund holdings, sectors, and recent NAV from Rupeestop by scheme ISIN."""

from __future__ import annotations

import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

import requests

from fund_data import (
    DATA_DIR,
    HOLDINGS_NAME,
    META_NAME,
    NAV_HISTORY_NAME,
    SECTOR_NAME,
)

ROOT = Path(__file__).resolve().parent
BASE_URL = "https://backend.rupeestop.com"
FUND_URL = BASE_URL + "/api/v1/app/fund/{isin}"
NAV_HISTORY_URL = BASE_URL + "/api/nav/{isin}/HISTORY"
NAV_LATEST_URL = BASE_URL + "/api/nav/{isin}/latest"
NAV_KEEP_CALENDAR_DAYS = 10
REQUEST_TIMEOUT = 45
ISIN_RE = re.compile(r"^[A-Z0-9]{12}$")

HOLDING_FIELDS = (
    "instrument_name",
    "percentage",
    "industry",
    "asset_type",
    "rating",
    "market_value",
    "fincode",
    "isin",
)


class FundFetchError(Exception):
    """Rupeestop request or payload could not be used."""


def normalize_isin(value: str) -> str:
    isin = str(value or "").strip().upper()
    if not ISIN_RE.fullmatch(isin):
        raise FundFetchError("Enter a 12-character ISIN, for example INF179K01UT0.")
    return isin


def _label(value) -> str:
    text = " ".join(str(value or "").split())
    if not text:
        return ""
    return text.replace("_", " ").title()


def _as_date(value) -> date:
    return date.fromisoformat(str(value)[:10])


def _get_json(url: str) -> dict:
    try:
        response = requests.get(url, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as exc:
        raise FundFetchError(f"Could not reach Rupeestop: {exc}") from exc
    if response.status_code == 404:
        raise FundFetchError("No fund found for that ISIN.")
    if response.status_code >= 400:
        raise FundFetchError(f"Rupeestop returned HTTP {response.status_code}.")
    try:
        payload = response.json()
    except ValueError as exc:
        raise FundFetchError("Rupeestop returned invalid JSON.") from exc
    if not isinstance(payload, dict) or payload.get("success") is False:
        raise FundFetchError(payload.get("message") or "Rupeestop request failed.")
    return payload


def fetch_latest_nav_date(isin: str) -> str:
    isin = normalize_isin(isin)
    payload = _get_json(NAV_LATEST_URL.format(isin=isin))
    data = payload.get("data") or {}
    nav_date = data.get("nav_date")
    if not nav_date:
        raise FundFetchError("Latest NAV date was missing.")
    return str(nav_date)[:10]


def fetch_fund_detail(isin: str) -> dict:
    isin = normalize_isin(isin)
    payload = _get_json(FUND_URL.format(isin=isin))
    data = payload.get("data")
    if not isinstance(data, dict):
        raise FundFetchError("Fund detail payload was empty.")
    return data


def fetch_nav_history(isin: str) -> list[dict]:
    isin = normalize_isin(isin)
    payload = _get_json(NAV_HISTORY_URL.format(isin=isin))
    data = payload.get("data") or {}
    records = data.get("records")
    if not isinstance(records, list) or not records:
        raise FundFetchError("NAV history was empty.")
    return records


def build_meta(isin: str, detail: dict) -> dict:
    identity = detail.get("identity") or {}
    plan = identity.get("plan") or ""
    option = identity.get("option") or ""
    fund_name = identity.get("fund_name") or identity.get("fund_short_name") or isin
    return {
        "isin": isin,
        "fund_name": fund_name,
        "plan": plan,
        "option": option,
        "plan_label": _label(plan),
        "option_label": _label(option),
    }


def extract_holdings(detail: dict) -> list[dict]:
    portfolio = detail.get("portfolio") or {}
    rows = portfolio.get("holdings")
    if not isinstance(rows, list) or not rows:
        raise FundFetchError("This fund has no holdings in the API.")
    holdings = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        holdings.append({field: row.get(field) for field in HOLDING_FIELDS})
    if not holdings:
        raise FundFetchError("This fund has no holdings in the API.")
    return holdings


def extract_sectors(detail: dict) -> list[dict]:
    allocations = detail.get("allocations") or {}
    rows = allocations.get("sector_from_holdings") or allocations.get("sector") or []
    sectors = []
    if not isinstance(rows, list):
        return sectors
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = row.get("sector") or ""
        if not name:
            continue
        try:
            percentage = float(row.get("percentage") or 0)
        except (TypeError, ValueError):
            percentage = 0.0
        sectors.append({"sector": name, "percentage": percentage})
    return sectors


def extract_nav_history(records: list[dict], keep_days: int = NAV_KEEP_CALENDAR_DAYS) -> list[dict]:
    cleaned = []
    for row in records:
        if not isinstance(row, dict):
            continue
        nav_date = row.get("nav_date")
        nav_value = row.get("nav_value")
        if not nav_date or nav_value is None:
            continue
        try:
            cleaned.append(
                {
                    "nav_date": str(nav_date)[:10],
                    "nav_value": float(nav_value),
                }
            )
        except (TypeError, ValueError):
            continue
    if not cleaned:
        raise FundFetchError("NAV history had no usable rows.")
    cleaned.sort(key=lambda row: row["nav_date"], reverse=True)
    latest = _as_date(cleaned[0]["nav_date"])
    cutoff = latest - timedelta(days=keep_days)
    kept = [row for row in cleaned if _as_date(row["nav_date"]) >= cutoff]
    return kept or cleaned[:1]


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def sync_fund(isin: str, data_root: Path = DATA_DIR) -> dict:
    """Pull both APIs and write data/<ISIN>/ files the pipeline already loads."""
    isin = normalize_isin(isin)
    detail = fetch_fund_detail(isin)
    meta = build_meta(isin, detail)
    holdings = extract_holdings(detail)
    sectors = extract_sectors(detail)
    nav_rows = extract_nav_history(fetch_nav_history(isin))
    dest = data_root / isin
    _write_json(dest / HOLDINGS_NAME, holdings)
    _write_json(dest / SECTOR_NAME, sectors)
    _write_json(dest / NAV_HISTORY_NAME, nav_rows)
    _write_json(dest / META_NAME, meta)
    return {
        "isin": isin,
        "meta": meta,
        "holdings_count": len(holdings),
        "sectors_count": len(sectors),
        "nav_start": nav_rows[-1]["nav_date"] if nav_rows else None,
        "nav_end": nav_rows[0]["nav_date"] if nav_rows else None,
        "nav_count": len(nav_rows),
        "data_dir": str(dest),
    }


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print("Usage: python rupeestop_fund.py <ISIN>", file=sys.stderr)
        return 1
    try:
        result = sync_fund(args[0])
    except FundFetchError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
