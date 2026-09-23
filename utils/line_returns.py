"""Return of a position that includes what was realised on partial sales.

"Return %" in the positions table compares today's price with the average
cost (PRU) of the shares still held. That is the right figure for a line that
was only ever bought. For a line that was reduced along the way it leaves out
the gain already taken: on 23 September Rocket Lab showed +7.35% while the
line had made +39.9% on the money put into it, because 40% of it had been sold
at $127.28 in May.

`adjusted_returns` gives, for each line that had at least one partial sale,
(proceeds from sales + current value - total invested) / total invested.
Lines without a sale get None and the table shows "—": their figure would be
identical to "Return %".
"""
from __future__ import annotations

import streamlit as st

BUY_ACTIONS = ("IN", "SWITCH")
SELL_ACTIONS = ("TRIM", "OUT")


def move_adjusted_return(trades: list, shares_now: float, price_now: float) -> float | None:
    """trades: [(side, shares, price)] with side 'buy' or 'sell', in date order.

    Returns the percentage, or None when the line had no sale or no cost.
    """
    if not any(side == "sell" for side, _, _ in trades):
        return None
    invested = sum(q * p for side, q, p in trades if side == "buy")
    proceeds = sum(q * p for side, q, p in trades if side == "sell")
    if invested <= 0:
        return None
    return (proceeds + shares_now * price_now - invested) / invested * 100


@st.cache_data(ttl=600)
def _trades_for(portfolio_id: str, tickers: tuple) -> dict:
    """{ticker: [(side, shares, price)]} rebuilt from the trade log and the ledger.

    The trade log carries the execution price; the number of shares traded is
    the change in the ledger's share count between the trade date and the
    previous row for that ticker (the ledger records shares, the log does not).
    """
    from utils.data import get_client
    sb = get_client()
    tx = (sb.table("transactions")
          .select("date,action,ticker_in,ticker_out,price_in,price_out")
          .eq("portfolio_id", portfolio_id).order("date").execute().data)

    out: dict = {}
    for tk in tickers:
        mine = [t for t in tx
                if (t.get("action") in BUY_ACTIONS and t.get("ticker_in") == tk)
                or (t.get("action") in SELL_ACTIONS and t.get("ticker_out") == tk)]
        if not any(t["action"] in SELL_ACTIONS for t in mine):
            continue
        rows = (sb.table("daily_holdings").select("date,shares")
                .eq("portfolio_id", portfolio_id).eq("ticker", tk)
                .order("date").execute().data)
        shares_on = {r["date"]: float(r["shares"] or 0) for r in rows}
        dates = sorted(shares_on)
        trades = []
        for t in mine:
            d = str(t["date"])
            if d not in shares_on:
                continue
            before = [x for x in dates if x < d]
            prev = shares_on[before[-1]] if before else 0.0
            delta = shares_on[d] - prev
            if t["action"] in BUY_ACTIONS and delta > 0 and t.get("price_in"):
                trades.append(("buy", delta, float(t["price_in"])))
            elif t["action"] in SELL_ACTIONS and delta < 0 and t.get("price_out"):
                trades.append(("sell", -delta, float(t["price_out"])))
        out[tk] = trades
    return out


def adjusted_returns(portfolio_id: str, positions: list) -> dict:
    """{ticker: percentage or None} for the positions table."""
    tickers = tuple(sorted(p["ticker"] for p in positions))
    try:
        trades = _trades_for(portfolio_id, tickers)
    except Exception:
        return {}
    result = {}
    for p in positions:
        tr = trades.get(p["ticker"])
        price, shares = p.get("current_price"), float(p.get("shares") or 0)
        if tr and price and shares > 0:
            v = move_adjusted_return(tr, shares, float(price))
            result[p["ticker"]] = round(v, 2) if v is not None else None
    return result
