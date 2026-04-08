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


@st.cache_data(ttl=3600)
def get_dividends_since(tickers: tuple, entry_dates: tuple) -> dict:
    """
    For each ticker, return total dividends per share received since entry_date.
    entry_dates is a tuple of ISO strings matching tickers order.
    Returns dict {ticker: total_dividends_per_share}.

    For STRC (Strategy STRETCH preferred): computed manually from 11.5% annual
    coupon on $100 par value, paid monthly, since entry date.
    """
    result = {}
    today = date.today()

    for ticker, entry_str in zip(tickers, entry_dates):
        try:
            # Manual calculation for STRC (preferred stock, yfinance unreliable)
            if ticker == "STRC":
                entry = date.fromisoformat(entry_str)
                days_held = (today - entry).days
                # 11.5% annual on $100 par = $11.50/year = $0.9583/month
                annual_yield = 11.5 / 100
                dividends_total = 100.0 * annual_yield * (days_held / 365.0)
                result[ticker] = round(dividends_total, 4)
                continue

            entry_ts = pd.Timestamp(entry_str)
            divs = yf.Ticker(ticker).dividends
            if divs.empty:
                result[ticker] = 0.0
                continue

            # Normalize timezone
            if divs.index.tz is not None:
                divs.index = divs.index.tz_localize(None)

            since = divs[divs.index >= entry_ts]
            result[ticker] = round(float(since.sum()), 4)

        except Exception:
            result[ticker] = 0.0

    return result
