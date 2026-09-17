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


def _signed_pct(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def article_matches_move_sentiment(target: dict, article: dict) -> bool:
    """
    Sentiment is checked against this name's weekly price, not the fund NAV.

    Falling stock/sector: keep only negative stories.
    Rising stock/sector: keep only positive stories (so offsets can appear
    in the summary when NAV is down).
    Flat or unknown: no sentiment gate.
    """
    change = _signed_pct(target.get("weekly_change_pct"))
    article_sentiment = (article.get("sentiment") or "").strip().lower()
    if change is None or change == 0:
        return True
    if change < 0:
        return article_sentiment == "negative"
    return article_sentiment == "positive"


def target_vs_nav_role(target: dict, official_nav_change: float) -> str:
    """drag = same direction as NAV; offset = moved the other way."""
    signed = _signed_pct(target.get("weekly_nav_impact_pct"))
    if signed is None:
        signed = _signed_pct(target.get("weekly_change_pct"))
    nav = _signed_pct(official_nav_change) or 0.0
    if signed is None or nav == 0:
        return "other"
    if nav < 0:
        return "offset" if signed > 0 else "drag"
    return "offset" if signed < 0 else "drag"


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


FINANCIAL_KEYWORDS = {
    "stock", "share", "shares", "equity", "market", "nifty", "sensex",
    "bse", "nse", "trading", "rally", "crash", "bull", "bear",
    "profit", "loss", "revenue", "earnings", "quarterly", "q1", "q2",
    "q3", "q4", "results", "dividend", "buyback", "bonus", "split",
    "merger", "acquisition", "takeover", "ipo", "listing", "delisting",
    "board", "agm", "ceo", "cfo", "chairman", "director", "resign",
    "appoint", "management",
    "rbi", "sebi", "regulatory", "regulation", "compliance", "penalty",
    "fine", "npa", "provisioning", "policy", "reform",
    "bond", "debt", "loan", "credit", "rating", "downgrade", "upgrade",
    "mutual fund", "etf", "futures", "options",
    "sector", "industry", "bank", "banking", "pharma", "technology",
    "energy", "infra", "infrastructure", "auto", "fmcg", "telecom",
    "fii", "dii", "institutional", "investor", "analyst", "target",
    "recommendation", "outlook", "forecast", "guidance",
    "reit", "realty", "nav",
}

MAX_EVENTS_PER_TARGET = 5
CAUSAL_SCORE_MIN = 5
ARTICLE_EXCERPT_CHARS = 400


def passes_keyword_filter(title: str, company_name: str, industry: str) -> bool:
    """Generous keep: company tokens, industry, financial terms, or figures."""
    title_lower = (title or "").lower()
    company_parts = (
        (company_name or "")
        .lower()
        .replace("ltd.", " ")
        .replace("ltd", " ")
        .replace("limited", " ")
        .split()
    )
    significant_parts = [part for part in company_parts if len(part) > 2]
    if any(part in title_lower for part in significant_parts):
        return True
    if industry and industry.lower() in title_lower:
        return True
    if any(keyword in title_lower for keyword in FINANCIAL_KEYWORDS):
        return True
    if any(marker in (title or "") for marker in ["₹", "Rs", "crore", "lakh", "%"]):
        return True
    return False


def filter_articles_by_keyword(articles: list[dict], name: str, industry: str) -> list[dict]:
    return [
        article
        for article in articles
        if passes_keyword_filter(article.get("title") or "", name, industry)
    ]


def _labels_match(label_a: str, label_b: str) -> bool:
    words_a = set((label_a or "").lower().split())
    words_b = set((label_b or "").lower().split())
    if not words_a or not words_b:
        return False
    overlap = len(words_a & words_b)
    smaller = min(len(words_a), len(words_b))
    return (overlap / smaller) >= 0.6


def group_by_event(scored_articles: list[dict]) -> dict[str, list[dict]]:
    groups = {}
    for article in scored_articles:
        label = (article.get("event_label") or "").strip().lower()
        if not label:
            label = (article.get("title") or "unlabeled")[:80].lower()
        matched = None
        for existing_label in groups:
            if _labels_match(label, existing_label):
                matched = existing_label
                break
        if matched:
            groups[matched].append(article)
        else:
            groups[label] = [article]
    return groups


def select_final_events(groups: dict, max_events: int = MAX_EVENTS_PER_TARGET) -> list[dict]:
    events = []
    for label, articles in groups.items():
        best = max(
            articles,
            key=lambda item: (
                float(item.get("causal_score") or 0),
                len(item.get("text") or ""),
            ),
        )
        events.append(
            {
                "event_label": best.get("event_label") or label,
                "event_summary": best.get("reasoning") or "",
                "combined_causal_score": best.get("causal_score"),
                "article_count": len(articles),
                "best_article": best,
            }
        )
    events.sort(key=lambda item: float(item.get("combined_causal_score") or 0), reverse=True)
    ranked = []
    for index, event in enumerate(events[:max_events], start=1):
        article = event["best_article"]
        ranked.append(
            {
                "event_rank": index,
                "event_label": event["event_label"],
                "event_summary": event["event_summary"],
                "article_count": event["article_count"],
                "title": article.get("title"),
                "source": article.get("source"),
                "published": article.get("published"),
                "date": article.get("date"),
                "link": article.get("link"),
                "resolved_url": article.get("resolved_url"),
                "text": (article.get("text") or "")[:ARTICLE_EXCERPT_CHARS],
                "relevancy_score": article.get("relevancy_score"),
                "causal_score": article.get("causal_score"),
                "causal_link": article.get("causal_link"),
                "timing_plausible": article.get("timing_plausible"),
                "sentiment": article.get("sentiment"),
                "reasoning": article.get("reasoning"),
            }
        )
    return ranked


IMPORTANT_NEWS_LIMIT = 8


def select_important_news(news_targets: list[dict], limit: int = IMPORTANT_NEWS_LIMIT) -> list[dict]:
    """One strongest kept article per event, then the top few by causal score."""
    candidates = []
    for target in news_targets:
        for item in target.get("relevant_news") or []:
            title = (item.get("title") or "").strip()
            url = (item.get("resolved_url") or item.get("link") or "").strip()
            if not title or not url:
                continue
            candidates.append(item)
    candidates.sort(key=lambda item: float(item.get("causal_score") or 0), reverse=True)
    picked = []
    seen_urls = set()
    seen_labels = set()
    for item in candidates:
        url = (item.get("resolved_url") or item.get("link") or "").strip()
        label = (item.get("event_label") or item.get("title") or "").strip().lower()
        if url in seen_urls or label in seen_labels:
            continue
        seen_urls.add(url)
        seen_labels.add(label)
        picked.append(
            {
                "title": (item.get("title") or "").strip(),
                "url": url,
                "source": (item.get("source") or "").strip(),
            }
        )
        if len(picked) >= limit:
            break
    return picked
