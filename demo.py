import json
import yfinance as yf
from stocks_for_news import get_top_3_nav_impact_holdings

# ---------------------------------------------------------
# FIND TICKER DYNAMICALLY
# ---------------------------------------------------------


def find_ticker(company_name):
    """
    Find the NSE ticker dynamically using the company name.

    The input only needs to contain the company name.

    Example:
        HDFC Bank Ltd -> HDFCBANK.NS
        ICICI Bank Ltd -> ICICIBANK.NS
        Infosys Ltd -> INFY.NS

    No company-specific ticker mappings are hardcoded.
    """

    if not company_name:
        return None

    try:
        print(f"Searching Yahoo for: {company_name}")

        search = yf.Search(company_name)

        quotes = search.quotes

        if not quotes:
            print(f"No Yahoo Finance results found for: {company_name}")
            return None

        # -------------------------------------------------
        # First look for NSE (.NS) stocks
        # -------------------------------------------------

        for quote in quotes:
            symbol = quote.get("symbol")

            if not symbol:
                continue

            if symbol.endswith(".NS"):
                print(f"Ticker found: {symbol}")
                return symbol

        print(f"No NSE ticker found for: {company_name}")
        return None

    except Exception as e:
        print(f"Error finding ticker for {company_name}: {e}")
        return None


# ---------------------------------------------------------
# GET LAST TWO TRADING-DAY CLOSES
# ---------------------------------------------------------


def get_last_two_closing_prices(ticker):
    """
    Get the latest two available trading-session closing prices.

    Uses Ticker.history() instead of yf.download().
    """

    try:

        stock = yf.Ticker(ticker)

        df = stock.history(period="10d", interval="1d", auto_adjust=False)

        if df.empty:
            print(f"No historical data returned for {ticker}")
            return None

        if "Close" not in df.columns:
            print(f"'Close' column not found for {ticker}")
            print(f"Available columns: {list(df.columns)}")
            return None

        # Remove missing closes
        df = df.dropna(subset=["Close"])

        if len(df) < 2:
            print(f"Less than two trading sessions " f"available for {ticker}")
            return None

        # Last two available trading sessions
        last_two = df.tail(2)

        prices = []

        for date, row in last_two.iterrows():

            close_price = float(row["Close"])

            # Remove timezone information if present
            if hasattr(date, "tz_localize"):

                try:
                    date = date.tz_localize(None)

                except Exception:
                    pass

            prices.append(
                {"date": date.strftime("%Y-%m-%d"), "close": round(close_price, 2)}
            )

        return prices

    except Exception as e:

        print(f"Error fetching prices for " f"{ticker}: {e}")

        return None


# ---------------------------------------------------------
# GET TOP 10
# ---------------------------------------------------------


def get_top_10_holdings(rows):
    """
    Sort holdings by NAV percentage and return top 10.
    """

    sorted_holdings = sorted(
        rows,
        key=lambda x: float(str(x["percentage"]).replace("%", "").strip()),
        reverse=True,
    )

    return sorted_holdings[:10]


# ---------------------------------------------------------
# CALCULATE NAV IMPACT
# ---------------------------------------------------------


def calculate_approx_nav_impact(nav_percentage, change_percentage):
    """
    Calculate the approximate contribution of a holding
    to the fund's NAV change.

    Formula:

        NAV Impact (%) =
            NAV Weight (%) * Stock Change (%) / 100

    Example:

        NAV weight = 9.31%
        Stock change = -1.27%

        Impact = 9.31 * -1.27 / 100
               = -0.118237%

    Returns:
        float: Approximate NAV impact percentage.
    """

    try:

        nav_percentage = float(nav_percentage)
        change_percentage = float(change_percentage)

        return round(nav_percentage * change_percentage / 100, 3)

    except (TypeError, ValueError):

        return 0.0


# ---------------------------------------------------------
# CALCULATE AVERAGE SIGNED NAV IMPACT
# ---------------------------------------------------------


def calculate_average_signed_nav_impact(holdings):
    """
    Calculate the average signed NAV impact
    across holdings.

    Positive values = positive contribution.

    Negative values = negative contribution.
    """

    if not holdings:
        return 0.0

    impacts = []

    for holding in holdings:

        impact = holding.get("nav_impact_percentage")

        if impact is not None:

            try:
                impacts.append(float(impact))

            except (TypeError, ValueError):
                continue

    if not impacts:
        return 0.0

    return round(sum(impacts) / len(impacts), 3)


# ---------------------------------------------------------
# MAIN FUND FUNCTION
# ---------------------------------------------------------


def get_fund_top_10_prices(fund_name, rows):
    """
    Get:

        - top 10 holdings
        - NAV percentage
        - dynamically discovered NSE ticker
        - latest two trading-day closing prices
        - percentage change
        - approximate NAV impact
        - average signed NAV impact
    """

    # -----------------------------------------------------
    # Get top 10 holdings
    # -----------------------------------------------------

    top_10 = get_top_10_holdings(rows)

    result = {"fund": fund_name, "top_10_holdings": []}

    print(f"\nFound {len(top_10)} top holdings.")

    # -----------------------------------------------------
    # Process every holding
    # -----------------------------------------------------

    for holding in top_10:

        name = holding["name"]
        industry = holding["detail"]
        nav_percentage = float(str(holding["percentage"]).replace("%", "").strip())

        print("\n" + "=" * 60)

        print(f"Processing: {name}")

        print(f"NAV percentage: " f"{nav_percentage}%")

        # -------------------------------------------------
        # Find ticker dynamically
        # -------------------------------------------------

        ticker = find_ticker(name)

        if not ticker:

            print(f"Ticker not found for: {name}")

            continue

        print(f"Using ticker: {ticker}")

        # -------------------------------------------------
        # Get prices
        # -------------------------------------------------

        prices = get_last_two_closing_prices(ticker)

        if not prices:

            print(f"Price data not found for: {name}")

            continue

        # prices are chronological:
        #
        # [older trading day, newer trading day]

        two_days_ago = prices[0]
        one_day_ago = prices[1]

        # -------------------------------------------------
        # Calculate percentage change
        # -------------------------------------------------

        two_day_close = two_days_ago["close"]
        one_day_close = one_day_ago["close"]

        if two_day_close == 0:

            print(f"Previous close is zero for: {name}")

            continue

        percentage_change = ((one_day_close - two_day_close) / two_day_close) * 100

        change_percentage = round(percentage_change, 2)

        # -------------------------------------------------
        # Calculate approximate NAV impact
        # -------------------------------------------------

        nav_impact_percentage = calculate_approx_nav_impact(
            nav_percentage, change_percentage
        )

        # -------------------------------------------------
        # Add result
        # -------------------------------------------------

        result["top_10_holdings"].append(
            {
                "name": name,
                "industry": industry,
                "nav_percentage": nav_percentage,
                "ticker": ticker,
                "change_percentage": change_percentage,
                "nav_impact_percentage": nav_impact_percentage,
            }
        )

    # -----------------------------------------------------
    # Calculate average signed NAV impact
    # -----------------------------------------------------

    result["average_signed_nav_impact"] = calculate_average_signed_nav_impact(
        result["top_10_holdings"]
    )

    return result


# =========================================================
# TEST
# =========================================================

if __name__ == "__main__":

    data = {
        "rows": [
            {
                "name": "HDFC Bank Ltd",
                "detail": "Financial Services",
                "percentage": "9.31%",
            },
            {
                "name": "ICICI Bank Ltd",
                "detail": "Financial Services",
                "percentage": "8.19%",
            },
            {
                "name": "Reliance Industries Ltd",
                "detail": "Energy",
                "percentage": "4.2%",
            },
            {
                "name": "Axis Bank Ltd",
                "detail": "Financial Services",
                "percentage": "4.06%",
            },
            {
                "name": "Bajaj Finance Ltd",
                "detail": "Financial Services",
                "percentage": "3.52%",
            },
            {
                "name": "Larsen & Toubro Ltd",
                "detail": "Industrials",
                "percentage": "3.47%",
            },
            {
                "name": "GE Vernova T&D India Ltd",
                "detail": "Industrials",
                "percentage": "2.81%",
            },
            {
                "name": "Sun Pharmaceuticals Industries Ltd",
                "detail": "Healthcare",
                "percentage": "2.8%",
            },
            {
                "name": "Infosys Ltd",
                "detail": "Technology",
                "percentage": "2.72%",
            },
            {
                "name": "Hindustan Unilever Ltd",
                "detail": "Consumer Defensive",
                "percentage": "2.71%",
            },
            {
                "name": "ITC Ltd",
                "detail": "Consumer Defensive",
                "percentage": "2.5%",
            },
            {
                "name": "Maruti Suzuki India Ltd",
                "detail": "Consumer Cyclical",
                "percentage": "2.44%",
            },
            {
                "name": "Mahindra & Mahindra Ltd",
                "detail": "Consumer Cyclical",
                "percentage": "2.35%",
            },
        ]
    }

    result = get_fund_top_10_prices(fund_name="Fund Name", rows=data["rows"])
    top_3_holdings = get_top_3_nav_impact_holdings(result)
    print("\n")
    print("=" * 70)
    print("FINAL RESULT")
    print("=" * 70)

    print(json.dumps(result, indent=2))

    print("\n")
    print("=" * 70)
    print("TOP 3 HOLDINGS BY NAV IMPACT")
    print("=" * 70)
    for holding in top_3_holdings:
        print(json.dumps(holding, indent=2))
