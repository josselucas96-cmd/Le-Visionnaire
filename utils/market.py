import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime


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
    all_tickers = list(set(list(tickers) + ["SPY"]))

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
