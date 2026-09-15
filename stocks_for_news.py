from fund_data import MIN_HOLDING_PCT, normalize_sector_label

SECTOR_SPREAD_MAX = 1.5


def get_top_3_nav_impact_holdings(fund_result):
    average_impact = fund_result.get("average_signed_nav_impact", 0)

    holdings = fund_result.get("top_10_holdings") or fund_result.get("holdings") or []

    if average_impact < 0:

        selected_holdings = [
            holding
            for holding in holdings
            if holding.get("nav_impact_percentage", 0) < 0
        ]

        # Most negative first
        selected_holdings.sort(key=lambda x: x.get("nav_impact_percentage", 0))

    elif average_impact > 0:

        selected_holdings = [
            holding
            for holding in holdings
            if holding.get("nav_impact_percentage", 0) > 0
        ]

        # Most positive first
        selected_holdings.sort(
            key=lambda x: x.get("nav_impact_percentage", 0), reverse=True
        )

    else:
        return []

    return selected_holdings[:3]


def weekly_change(holding: dict) -> float:
    return float(holding.get("weekly_change_pct") or 0)


def weekly_impact(holding: dict) -> float:
    if holding.get("weekly_nav_impact_pct") is not None:
        return float(holding["weekly_nav_impact_pct"])
    return float(holding.get("nav_impact_percentage") or 0)


def preferred_sentiment(change_pct, official_nav_change: float) -> str:
    if change_pct is None:
        return "negative" if official_nav_change < 0 else "positive"
    if change_pct < 0:
        return "negative"
    if change_pct > 0:
        return "positive"
    return "negative" if official_nav_change < 0 else "positive"


def group_priced_by_industry(holdings: list[dict]) -> dict[str, list[dict]]:
    groups = {}
    for holding in holdings:
        key = normalize_sector_label(holding.get("industry"))
        if not key:
            continue
        groups.setdefault(key, []).append(holding)
    return groups


def classify_industry_scope(members: list[dict]) -> tuple[str, float | None]:
    """
    sector_wide: 2+ priced names, all same sign, spread < 1.5%.
    single: 0 or 1 priced name.
    mixed: 2+ names that disagree or spread is wide.
    """
    if len(members) < 2:
        return "single", None

    changes = [weekly_change(item) for item in members]
    signs = []
    for change in changes:
        if change > 0:
            signs.append(1)
        elif change < 0:
            signs.append(-1)
        else:
            signs.append(0)

    if any(sign == 0 for sign in signs):
        return "mixed", round(max(changes) - min(changes), 2)

    same_direction = all(sign == signs[0] for sign in signs)
    spread = round(max(changes) - min(changes), 2)
    if same_direction and spread < SECTOR_SPREAD_MAX:
        return "sector_wide", spread
    return "mixed", spread


def build_sector_moves(priced_holdings: list[dict], large_sectors: list[dict]) -> list[dict]:
    groups = group_priced_by_industry(priced_holdings)
    moves = []
    for sector in large_sectors:
        if sector.get("overseas"):
            continue
        key = sector.get("normalized") or normalize_sector_label(sector.get("sector"))
        members = groups.get(key, [])
        if members:
            scope, spread = classify_industry_scope(members)
            avg_change = round(
                sum(weekly_change(item) for item in members) / len(members), 2
            )
        else:
            scope, spread, avg_change = "no_priced_names", None, None
        moves.append(
            {
                "sector": sector.get("sector"),
                "normalized": key,
                "fund_weight_pct": sector.get("percentage"),
                "scope": scope,
                "spread_pct": spread,
                "avg_weekly_change_pct": avg_change,
                "members": [
                    {
                        "name": item.get("name"),
                        "nav_percentage": item.get("nav_percentage"),
                        "weekly_change_pct": weekly_change(item),
                        "weekly_nav_impact_pct": weekly_impact(item),
                    }
                    for item in sorted(
                        members,
                        key=lambda item: item.get("nav_percentage") or 0,
                        reverse=True,
                    )
                ],
            }
        )
    return moves


def _compact_holding(holding: dict) -> dict:
    return {
        "name": holding.get("name"),
        "industry": holding.get("industry"),
        "ticker": holding.get("ticker"),
        "nav_percentage": holding.get("nav_percentage"),
        "weekly_change_pct": weekly_change(holding),
        "weekly_nav_impact_pct": weekly_impact(holding),
    }


def select_offsets(headline_holdings: list[dict], official_nav_change: float) -> list[dict]:
    """Holdings whose impact cushions the official NAV move."""
    if official_nav_change < 0:
        offsets = [h for h in headline_holdings if weekly_impact(h) > 0]
        offsets.sort(key=weekly_impact, reverse=True)
    elif official_nav_change > 0:
        offsets = [h for h in headline_holdings if weekly_impact(h) < 0]
        offsets.sort(key=weekly_impact)
    else:
        offsets = []
    return [_compact_holding(item) for item in offsets]


def select_drags(headline_holdings: list[dict], official_nav_change: float) -> list[dict]:
    """Holdings whose impact is in the same direction as official NAV."""
    if official_nav_change < 0:
        drags = [h for h in headline_holdings if weekly_impact(h) < 0]
        drags.sort(key=weekly_impact)
    elif official_nav_change > 0:
        drags = [h for h in headline_holdings if weekly_impact(h) > 0]
        drags.sort(key=weekly_impact, reverse=True)
    else:
        drags = []
    return [_compact_holding(item) for item in drags]


def select_news_targets(
    headline_holdings: list[dict],
    sector_moves: list[dict],
    official_nav_change: float,
) -> list[dict]:
    """
    Sector-wide industries get one sector target (no per-stock news).
    Other ≥2% names get stock targets.
    ≥3% domestic sectors with no ≥2% name (e.g. Pharma) get a sector target.
    """
    sector_wide_keys = {
        move["normalized"] for move in sector_moves if move.get("scope") == "sector_wide"
    }
    targets = []

    for move in sector_moves:
        if move.get("scope") != "sector_wide":
            continue
        targets.append(
            {
                "type": "sector",
                "name": move["sector"],
                "industry": move["sector"],
                "scope": "sector_wide",
                "fund_weight_pct": move.get("fund_weight_pct"),
                "weekly_change_pct": move.get("avg_weekly_change_pct"),
                "target_sentiment": preferred_sentiment(
                    move.get("avg_weekly_change_pct"), official_nav_change
                ),
                "members": [member["name"] for member in move.get("members", [])],
            }
        )

    stock_moves = []
    for holding in headline_holdings:
        key = normalize_sector_label(holding.get("industry"))
        if key in sector_wide_keys:
            continue
        stock_moves.append(
            {
                "type": "stock",
                "name": holding.get("name"),
                "industry": holding.get("industry") or "",
                "scope": "company_specific",
                "nav_percentage": holding.get("nav_percentage"),
                "ticker": holding.get("ticker"),
                "weekly_change_pct": weekly_change(holding),
                "weekly_nav_impact_pct": weekly_impact(holding),
                "target_sentiment": preferred_sentiment(
                    weekly_change(holding), official_nav_change
                ),
            }
        )
    targets.extend(stock_moves)

    headline_keys = {
        normalize_sector_label(holding.get("industry")) for holding in headline_holdings
    }
    for move in sector_moves:
        key = move.get("normalized")
        if move.get("scope") == "sector_wide":
            continue
        if key in headline_keys:
            continue
        targets.append(
            {
                "type": "sector",
                "name": move["sector"],
                "industry": move["sector"],
                "scope": move.get("scope"),
                "fund_weight_pct": move.get("fund_weight_pct"),
                "weekly_change_pct": move.get("avg_weekly_change_pct"),
                "target_sentiment": preferred_sentiment(
                    move.get("avg_weekly_change_pct"), official_nav_change
                ),
                "members": [member["name"] for member in move.get("members", [])],
            }
        )

    return targets


def headline_holdings(priced_holdings: list[dict]) -> list[dict]:
    selected = [
        holding
        for holding in priced_holdings
        if float(holding.get("nav_percentage") or 0) >= MIN_HOLDING_PCT
    ]
    selected.sort(key=lambda item: item.get("nav_percentage") or 0, reverse=True)
    return selected
