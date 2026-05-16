import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime, date


@st.cache_data(ttl=3600)  # Refresh every hour — fundamentals don't move intraday
def get_valuation_fundamentals(tickers: tuple) -> dict:
    """For each ticker, return a dict with the fields needed by the Valo
    Tracking table. Margins are returned as ratios 0-1 (caller multiplies
    by 100 if it wants percentages). Missing fields are returned as None
    rather than raising — yfinance is patchy on non-US tickers.
    """
    result = {}
    for t in tickers:
        try:
            tk = yf.Ticker(t)
            info = tk.info
            rev = info.get("totalRevenue")
            fcf = info.get("freeCashflow")
            fcf_margin = (fcf / rev) if (rev and fcf is not None and rev > 0) else None

            # Analyst consensus revenue growth (forward, +1y).
            analyst_rg = None
            try:
                rev_est = tk.revenue_estimate
                if rev_est is not None and not rev_est.empty:
                    if "+1y" in rev_est.index and "growth" in rev_est.columns:
                        g = rev_est.loc["+1y", "growth"]
                        if pd.notna(g):
                            analyst_rg = float(g) * 100
                    if analyst_rg is None and "+1y" in rev_est.index and "0y" in rev_est.index:
                        cur = rev_est.loc["0y", "avg"]
                        nxt = rev_est.loc["+1y", "avg"]
                        if pd.notna(cur) and pd.notna(nxt) and cur > 0:
                            analyst_rg = (float(nxt) - float(cur)) / float(cur) * 100
            except Exception:
                pass
            # Fallback to TTM revenue growth from .info (backward-looking but better than nothing)
            if analyst_rg is None and info.get("revenueGrowth") is not None:
                analyst_rg = float(info["revenueGrowth"]) * 100

            result[t] = {
                "market_cap":       info.get("marketCap"),
                "enterprise_value": info.get("enterpriseValue"),
                "revenue_ttm":      rev,
                "ebitda":           info.get("ebitda"),
                "gross_margin":     info.get("grossMargins"),
                "operating_margin": info.get("operatingMargins"),
                "free_cashflow":    fcf,
                "fcf_margin":       fcf_margin,
                "forward_pe":       info.get("forwardPE"),
                "trailing_pe":      info.get("trailingPE"),
                "analyst_rg":       analyst_rg,
            }
        except Exception:
            result[t] = {"market_cap": None, "enterprise_value": None,
                         "revenue_ttm": None, "ebitda": None,
                         "gross_margin": None, "operating_margin": None,
                         "free_cashflow": None, "fcf_margin": None,
                         "forward_pe": None, "trailing_pe": None,
                         "analyst_rg": None}
    return result


@st.cache_data(ttl=300)  # Refresh every 5 minutes
def get_prices(tickers: tuple) -> dict:
    """[LEGACY — live yfinance] Current price, daily % change, market cap
    (in listing currency) and currency code for each ticker.

    Each call hits yfinance N times (sequential). Slow at scale + risk of
    Yahoo rate-limiting. See `get_prices_from_db` for the cached version
    that reads from Supabase (populated by daily_refresh.py cron).

    Kept for the Admin cockpit move-execution flow which needs truly live
    prices at commit time (not EOD).
    """
    result = {}
    for ticker in tickers:
        try:
            info = yf.Ticker(ticker).fast_info
            price = info.last_price
            prev = info.previous_close
            mc   = getattr(info, "market_cap", None)
            ccy  = getattr(info, "currency", None)
            result[ticker] = {
                "price": round(price, 2),
                "change_pct": round((price - prev) / prev * 100, 2),
                "market_cap": float(mc) if mc is not None else None,
                "currency":   ccy or "USD",
            }
        except Exception:
            result[ticker] = {"price": None, "change_pct": None,
                              "market_cap": None, "currency": None}
    return result


@st.cache_data(ttl=600)  # Refresh every 10 min — cron writes every 24h
def get_prices_from_db(tickers: tuple) -> dict:
    """[NEW] Read prices from Supabase `current_prices` table.

    Populated by daily_refresh.py cron (GitHub Action, 22:07 UTC daily).
    No yfinance calls here → fast (single Supabase query) and no rate-limit
    risk. Trade-off: prices are EOD (last close), not intraday-live.

    Returns the same dict shape as `get_prices` so callers can swap with a
    one-line import change.

    Tickers missing from the table (e.g., newly added position not yet
    fetched by the cron) get {price: None, ...} so caller can fall back.
    """
    from utils.data import get_client
    sb = get_client()
    if not tickers:
        return {}

    try:
        rows = (
            sb.table("current_prices")
            .select("ticker, price, change_pct, market_cap, currency")
            .in_("ticker", list(tickers))
            .execute()
            .data
        )
    except Exception:
        # If the table doesn't exist yet or DB is down, return all-None
        # so the caller can fall back to get_prices (yfinance) gracefully.
        return {tk: {"price": None, "change_pct": None,
                     "market_cap": None, "currency": None} for tk in tickers}

    by_ticker = {r["ticker"]: r for r in rows}
    result = {}
    for tk in tickers:
        r = by_ticker.get(tk)
        if r is None:
            result[tk] = {"price": None, "change_pct": None,
                          "market_cap": None, "currency": None}
        else:
            result[tk] = {
                "price":      round(float(r["price"]), 2) if r["price"] is not None else None,
                "change_pct": round(float(r["change_pct"]), 2) if r["change_pct"] is not None else None,
                "market_cap": float(r["market_cap"]) if r["market_cap"] is not None else None,
                "currency":   r["currency"] or "USD",
            }
    return result


# Approximate BTC holdings per Nakamoto position. Estimates as of Q3 2025
# disclosures — UPDATE FROM ACTUAL FILINGS as positions evolve. STRC is a
# preferred share with no direct BTC exposure (holders earn USD coupons).
BTC_HOLDINGS_NAKAMOTO = {
    "MSTR":     597325,  # Strategy (ex-MicroStrategy)
    "MTPLF":     22610,  # Metaplanet (3350.T OTC US line)
    "ASST":       5816,  # Strive Asset Management (post-Asset Entities)
    "ALCPB.PA":   2089,  # Capital B (ex Blockchain Group)
    "OBTC3.SA":    800,  # OranjeBTC (B3 Brazil) — estimate, verify
    "GS9.F":       800,  # H100 Group (Frankfurt OTC) — estimate, verify
    "CASH3.SA":    320,  # Méliuz (B3 Brazil)
    "SWC.L":      2500,  # Smarter Web Company (LSE) — estimate, verify
    "STRC":          0,  # Preferred — no direct BTC exposure
}


@st.cache_data(ttl=300)  # Refresh every 5 minutes
def get_bitcoin_price() -> float | None:
    """Current BTC-USD spot price. Used for Nakamoto NAV computations."""
    try:
        return float(yf.Ticker("BTC-USD").fast_info.last_price)
    except Exception:
        return None


@st.cache_data(ttl=3600)  # FX rates don't move much intraday
def get_fx_to_usd(currencies: tuple) -> dict:
    """Returns {currency_code: rate_to_usd}. USD maps to 1.0; unknown / failed
    lookups map to None so the caller can show '—' instead of a wrong figure.
    """
    result = {"USD": 1.0}
    for ccy in currencies:
        if not ccy or ccy == "USD" or ccy in result:
            continue
        try:
            pair = f"{ccy}USD=X"
            info = yf.Ticker(pair).fast_info
            rate = info.last_price
            result[ccy] = float(rate) if rate else None
        except Exception:
            result[ccy] = None
    return result


@st.cache_data(ttl=3600)  # Refresh every hour
def get_history(tickers: tuple, start: str, benchmarks: tuple = ("SPY", "QQQ")) -> pd.DataFrame:
    """
    Daily closing prices for tickers + benchmarks from start to today.
    Returns a DataFrame with tickers as columns, date as index.
    Missing tickers are silently dropped.

    `benchmarks` defaults to ('SPY', 'QQQ') for backwards compat (Visionnaire).
    Pass ('BTC-USD', 'MSTR') for Le Nakamoto, etc.
    """
    end = datetime.today().strftime("%Y-%m-%d")
    all_tickers = list(set(list(tickers) + list(benchmarks)))

    try:
        raw = yf.download(all_tickers, start=start, end=end,
                          auto_adjust=True, progress=False)

        # yfinance returns MultiIndex columns when multiple tickers
        if isinstance(raw.columns, pd.MultiIndex):
            raw = raw["Close"]
        else:
            # Single ticker: raw is a DataFrame with OHLCV columns
            raw = raw[["Close"]].rename(columns={"Close": all_tickers[0]})

        # Normalize index to date-only (strip timezone + time component)
        if raw.index.tz is not None:
            raw.index = raw.index.tz_localize(None)
        raw.index = pd.to_datetime(raw.index.date)
        return raw.dropna(how="all")
    except Exception:
        return pd.DataFrame()


# STRC monthly dividend schedule: ~$0.9583/share on the last business day of each month
# (11.5% annual on $100 par = $11.50/yr / 12 months)
STRC_MONTHLY_DIV = 100.0 * 0.115 / 12  # ≈ 0.9583 per share per month


def _strc_dividend_dates(entry_str: str) -> list[tuple]:
    """
    Return list of (payment_date, div_per_share) for STRC since entry_date.
    STRC pays on the last business day of each month.
    Only includes months that have fully elapsed (payment date <= today).
    """
    from pandas.tseries.offsets import BMonthEnd
    entry = pd.Timestamp(entry_str)
    today = pd.Timestamp(date.today())
    payments = []
    # Start from end of month of entry
    payment = entry + BMonthEnd(1)
    while payment <= today:
        payments.append((payment, STRC_MONTHLY_DIV))
        payment = payment + BMonthEnd(1)
    return payments


@st.cache_data(ttl=3600)
def get_total_return_factor(tickers: tuple, entry_dates: tuple, prices_at_entry: tuple) -> dict:
    """
    Compute total return factor for each ticker assuming dividend reinvestment.

    For each dividend payment since entry:
        shares multiplied by (1 + div_per_share / price_on_payment_date)

    Returns dict {ticker: {"shares_factor": float, "div_return_pct": float}}
    where shares_factor = accumulated shares per initial share (>= 1.0)
    and div_return_pct = (shares_factor - 1) * 100
    """
    result = {}
    today_str = date.today().isoformat()

    for ticker, entry_str, entry_price in zip(tickers, entry_dates, prices_at_entry):
        try:
            if ticker == "STRC":
                payments = _strc_dividend_dates(entry_str)
                if not payments:
                    result[ticker] = {"shares_factor": 1.0, "div_return_pct": 0.0}
                    continue
                # Need price history for STRC on payment dates
                hist = yf.download("STRC", start=entry_str, end=today_str,
                                   auto_adjust=True, progress=False)
                if isinstance(hist.columns, pd.MultiIndex):
                    hist = hist["Close"]["STRC"]
                else:
                    hist = hist["Close"]
                hist.index = hist.index.tz_localize(None) if hist.index.tz else hist.index

                shares = 1.0
                for pay_date, div in payments:
                    # Price on or before payment date
                    available = hist[hist.index <= pay_date]
                    price_on_day = float(available.iloc[-1]) if not available.empty else 100.0
                    shares *= (1 + div / price_on_day)

                result[ticker] = {
                    "shares_factor": round(shares, 6),
                    "div_return_pct": round((shares - 1) * 100, 4),
                }
                continue

            entry_ts = pd.Timestamp(entry_str)
            divs = yf.Ticker(ticker).dividends
            if divs.empty:
                result[ticker] = {"shares_factor": 1.0, "div_return_pct": 0.0}
                continue

            # Normalize timezone
            if divs.index.tz is not None:
                divs.index = divs.index.tz_localize(None)
            since = divs[divs.index >= entry_ts]

            if since.empty:
                result[ticker] = {"shares_factor": 1.0, "div_return_pct": 0.0}
                continue

            # Get price history for reinvestment pricing
            hist = yf.download(ticker, start=entry_str, end=today_str,
                               auto_adjust=True, progress=False)
            if isinstance(hist.columns, pd.MultiIndex):
                hist = hist["Close"][ticker]
            else:
                hist = hist["Close"]
            if hist.index.tz is not None:
                hist.index = hist.index.tz_localize(None)

            shares = 1.0
            for pay_date, div in since.items():
                available = hist[hist.index <= pay_date]
                if available.empty:
                    continue
                price_on_day = float(available.iloc[-1])
                if price_on_day > 0:
                    shares *= (1 + div / price_on_day)

            result[ticker] = {
                "shares_factor": round(shares, 6),
                "div_return_pct": round((shares - 1) * 100, 4),
            }

        except Exception:
            result[ticker] = {"shares_factor": 1.0, "div_return_pct": 0.0}

    return result
