def get_top_3_nav_impact_holdings(fund_result):
    average_impact = fund_result.get("average_signed_nav_impact", 0)

    holdings = fund_result.get("top_10_holdings", [])

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
