"""Load fund holdings, NAV history, and sector weights from data/*.json."""

import json
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"

HOLDINGS_FILE = DATA_DIR / "fund_holding_data.json"
NAV_HISTORY_FILE = DATA_DIR / "fund_nav_history.json"
SECTOR_FILE = DATA_DIR / "fund_sector.json"
HOLDINGS_NAME = HOLDINGS_FILE.name
NAV_HISTORY_NAME = NAV_HISTORY_FILE.name
SECTOR_NAME = SECTOR_FILE.name

EQUITY_ASSET_TYPES = {"Domestic Equities", "REITs & InvITs"}
MIN_HOLDING_PCT = 2.0
MIN_SECTOR_PCT = 3.0
NAV_WEEK_CALENDAR_DAYS = 7


def parse_nav_percentage(value) -> float:
    """Accept a float or a string like '9.31%'."""
    try:
        return float(str(value).replace("%", "").strip())
    except (TypeError, ValueError):
        return 0.0


def _as_date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def normalize_sector_label(label) -> str:
    """Lowercase, strip '##' suffixes, collapse whitespace for matching."""
    if not label:
        return ""
    text = str(label).replace("##", " ")
    text = " ".join(text.split()).strip().lower()
    return text


def _read_json_array(path: Path) -> list:
    if not path.exists():
        raise FileNotFoundError(f"Fund data file not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"Expected a JSON array in {path}")
    return data


def load_holdings(path: Path = HOLDINGS_FILE) -> list[dict]:
    return _read_json_array(path)


def load_nav_history(path: Path = NAV_HISTORY_FILE) -> list[dict]:
    rows = _read_json_array(path)
    return sorted(rows, key=lambda row: row["nav_date"])


def load_sectors(path: Path = SECTOR_FILE) -> list[dict]:
    sectors = []
    for row in _read_json_array(path):
        name = row.get("sector") or ""
        sectors.append(
            {
                "sector": name,
                "percentage": parse_nav_percentage(row.get("percentage", 0)),
                "normalized": normalize_sector_label(name),
                "overseas": "##" in str(name),
            }
        )
    return sectors


def to_pipeline_row(holding: dict) -> dict:
    """Map fund JSON fields onto the pipeline {name, detail, percentage} shape."""
    return {
        "name": holding.get("instrument_name") or "",
        "detail": holding.get("industry") or "",
        "percentage": holding.get("percentage", 0),
        "asset_type": holding.get("asset_type"),
        "industry": holding.get("industry") or "",
        "fincode": holding.get("fincode"),
    }


def is_equity_like(holding: dict) -> bool:
    return holding.get("asset_type") in EQUITY_ASSET_TYPES


def equity_like_holdings(holdings: list[dict]) -> list[dict]:
    return [h for h in holdings if is_equity_like(h)]


def holdings_at_least(holdings: list[dict], min_pct: float = MIN_HOLDING_PCT) -> list[dict]:
    selected = [
        h
        for h in holdings
        if parse_nav_percentage(h.get("percentage", 0)) >= min_pct
    ]
    selected.sort(key=lambda h: parse_nav_percentage(h.get("percentage", 0)), reverse=True)
    return selected


def sectors_at_least(sectors: list[dict], min_pct: float = MIN_SECTOR_PCT) -> list[dict]:
    selected = [s for s in sectors if s.get("percentage", 0) >= min_pct]
    selected.sort(key=lambda s: s.get("percentage", 0), reverse=True)
    return selected


def holdings_for_weekly_prices(holdings: list[dict]) -> list[dict]:
    """Domestic equities + REITs with weight >= 2%, mapped for demo.py."""
    return [
        to_pipeline_row(h)
        for h in holdings_at_least(equity_like_holdings(holdings), MIN_HOLDING_PCT)
    ]


def holdings_for_price_universe(
    holdings: list[dict],
    large_sectors: list[dict],
) -> list[dict]:
    """
    Price ≥2% equity-like names, plus smaller names in ≥3% domestic sectors
    so sector-wide vs mixed classification has enough peers.
    """
    large_norms = {
        row["normalized"]
        for row in large_sectors
        if row.get("normalized") and not row.get("overseas")
    }
    selected = []
    seen = set()
    for holding in equity_like_holdings(holdings):
        pct = parse_nav_percentage(holding.get("percentage", 0))
        industry_key = normalize_sector_label(holding.get("industry"))
        if pct < MIN_HOLDING_PCT and industry_key not in large_norms:
            continue
        row = to_pipeline_row(holding)
        name = row["name"]
        if not name or name in seen:
            continue
        seen.add(name)
        selected.append(row)
    selected.sort(key=lambda row: parse_nav_percentage(row["percentage"]), reverse=True)
    return selected


def official_nav_week(
    nav_rows: list[dict],
    calendar_days: int = NAV_WEEK_CALENDAR_DAYS,
) -> dict:
    """
    Week end = newest NAV date.
    Week start = NAV on or closest-before (week_end - calendar_days).
    """
    if not nav_rows:
        raise ValueError("NAV history is empty")

    ordered = sorted(nav_rows, key=lambda row: row["nav_date"])
    end_row = ordered[-1]
    week_end = _as_date(end_row["nav_date"])
    target_start = week_end - timedelta(days=calendar_days)

    start_candidates = [
        row for row in ordered if _as_date(row["nav_date"]) <= target_start
    ]
    start_row = start_candidates[-1] if start_candidates else ordered[0]
    week_start = _as_date(start_row["nav_date"])

    start_nav = float(start_row["nav_value"])
    end_nav = float(end_row["nav_value"])
    if start_nav == 0:
        change_pct = 0.0
    else:
        change_pct = round((end_nav - start_nav) / start_nav * 100, 3)

    return {
        "start": week_start.isoformat(),
        "end": week_end.isoformat(),
        "start_nav": start_nav,
        "end_nav": end_nav,
        "change_pct": change_pct,
    }


def available_fund_ids() -> list[str]:
    """Subfolders of data/ that contain fund_holding_data.json."""
    if not DATA_DIR.exists():
        return []
    ids = []
    for path in sorted(DATA_DIR.iterdir()):
        if path.is_dir() and (path / HOLDINGS_NAME).exists():
            ids.append(path.name)
    return ids


def resolve_fund_data_dir(fund_id: str | None = None) -> Path:
    """data/<fund_id>/ when a flag is passed, else the data/ root JSON files."""
    if not fund_id:
        return DATA_DIR
    data_dir = DATA_DIR / fund_id
    if not (data_dir / HOLDINGS_NAME).exists():
        known = ", ".join(f"--{fid}" for fid in available_fund_ids()) or "(none)"
        raise FileNotFoundError(
            f"No fund data at {data_dir}. Known funds: {known}"
        )
    return data_dir


def load_fund_bundle(data_dir: Path = DATA_DIR) -> dict:
    holdings = load_holdings(data_dir / HOLDINGS_NAME)
    nav_history = load_nav_history(data_dir / NAV_HISTORY_NAME)
    sectors = load_sectors(data_dir / SECTOR_NAME)
    large_sectors = sectors_at_least(sectors)
    return {
        "holdings": holdings,
        "nav_history": nav_history,
        "sectors": sectors,
        "official_nav": official_nav_week(nav_history),
        "large_sectors": large_sectors,
        "price_rows": holdings_for_weekly_prices(holdings),
        "price_universe": holdings_for_price_universe(holdings, large_sectors),
    }
