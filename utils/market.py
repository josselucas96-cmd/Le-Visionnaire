import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime, date


@st.cache_data(ttl=300)  # Refresh every 5 minutes
def get_prices(tickers: tuple) -> dict:
    """Current price and daily % change for each ticker."""
    result = {}
    for ticker in tickers:
        try:
            info = yf.Ticker(ticker).fast_info
            price = info.last_price
            prev = info.previous_close
            result[ticker] = {
                "price": round(price, 2),
                "change_pct": round((price - prev) / prev * 100, 2),
            }
        except Exception:
            result[ticker] = {"price": None, "change_pct": None}
    return result


@st.cache_data(ttl=3600)  # Refresh every hour
def get_history(tickers: tuple, start: str) -> pd.DataFrame:
    """
    Daily closing prices for all tickers + SPY from start to today.
    Returns a DataFrame with tickers as columns, date as index.
    Missing tickers are silently dropped.
    """
    end = datetime.today().strftime("%Y-%m-%d")
    all_tickers = list(set(list(tickers) + ["SPY", "QQQ"]))

    try:
        raw = yf.download(all_tickers, start=start, end=end,
                          auto_adjust=True, progress=False)

        # yfinance returns MultiIndex columns when multiple tickers
        if isinstance(raw.columns, pd.MultiIndex):
            raw = raw["Close"]
        else:
            # Single ticker: raw is a DataFrame with OHLCV columns
            raw = raw[["Close"]].rename(columns={"Close": all_tickers[0]})

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
