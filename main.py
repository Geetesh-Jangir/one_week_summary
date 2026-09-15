"""
Main entry point: weekly fund prices from data/*.json (Phase 1).

News, scraping, and Groq scoring are not run in this phase.
"""

import json
import logging
import io
import contextlib
from pathlib import Path

from fund_data import load_fund_bundle
from demo import get_fund_weekly_prices

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent
OUTPUT_SCRAPPER_DIR = ROOT / "output-scrapper"


def sort_by_weekly_nav_impact(holdings: list[dict]) -> list[dict]:
    """Negatives first (most negative), then positives (highest first)."""
    negative = [h for h in holdings if h.get("weekly_nav_impact_pct", 0) < 0]
    positive = [h for h in holdings if h.get("weekly_nav_impact_pct", 0) >= 0]
    negative.sort(key=lambda x: x.get("weekly_nav_impact_pct", 0))
    positive.sort(key=lambda x: x.get("weekly_nav_impact_pct", 0), reverse=True)
    return negative + positive


def main():
    logger.info("Loading fund holdings, NAV history, and sectors from data/")
    bundle = load_fund_bundle()
    official_nav = bundle["official_nav"]
    price_rows = bundle["price_rows"]
    large_sectors = [
        {
            "sector": row["sector"],
            "percentage": row["percentage"],
            "overseas": row["overseas"],
        }
        for row in bundle["large_sectors"]
    ]

    logger.info(
        "Official NAV week %s to %s (%s -> %s, %s%%)",
        official_nav["start"],
        official_nav["end"],
        official_nav["start_nav"],
        official_nav["end_nav"],
        official_nav["change_pct"],
    )
    logger.info(
        "Pricing %s domestic equity/REIT holdings with weight >= 2%%",
        len(price_rows),
    )

    with contextlib.redirect_stdout(io.StringIO()):
        fund_result = get_fund_weekly_prices(
            "Fund",
            price_rows,
            official_nav["start"],
            official_nav["end"],
        )

    holdings = sort_by_weekly_nav_impact(fund_result.get("holdings", []))
    skipped = fund_result.get("skipped", [])

    logger.info(
        "Priced %s holdings, skipped %s, approx equity impact %s%% vs official NAV %s%%",
        len(holdings),
        len(skipped),
        fund_result.get("approx_equity_impact_pct"),
        official_nav["change_pct"],
    )

    output = {
        "week": {
            "start": official_nav["start"],
            "end": official_nav["end"],
        },
        "official_nav": official_nav,
        "approx_equity_impact_pct": fund_result.get("approx_equity_impact_pct", 0.0),
        "average_signed_nav_impact": fund_result.get("average_signed_nav_impact", 0.0),
        "holdings": holdings,
        "skipped": skipped,
        "sectors": large_sectors,
    }

    OUTPUT_SCRAPPER_DIR.mkdir(parents=True, exist_ok=True)
    result_json_path = OUTPUT_SCRAPPER_DIR / "result.json"
    result_json_str = json.dumps(output, indent=2, ensure_ascii=False)
    result_json_path.write_text(result_json_str, encoding="utf-8")
    logger.info("Saved Phase 1 result JSON to %s", result_json_path)
    print(result_json_str)


if __name__ == "__main__":
    main()
