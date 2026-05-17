"""NAV snapshot persistence — daily portfolio value frozen in DB.

Once a row is written for (portfolio_id, date), it is never recomputed.
Future moves (which mutate weight / PRU) only affect days from the move
forward — historical NAV is immutable. This is what makes the chart
stable across moves.

The series persisted matches `build_portfolio_index` (legacy weight-based
buy-and-hold index): each position normalized to 100 at its first
available price >= entry_date, then weight-averaged. Cash sits implicitly
at 100.

units / cash_units (from PR-1) are kept on the schema for cost-basis
tracking and future work — they are not used here. The chart deliberately
stays on the legacy formula in PR-2 to avoid behavior changes; PR-3 may
revisit if the move semantics require it.
"""
import pandas as pd
import streamlit as st

from utils.data import get_client
from utils.metrics import build_portfolio_index


@st.cache_data(ttl=120)
def get_nav_series(portfolio_id: str) -> pd.Series:
    """[LEGACY] Read NAV history for this portfolio (cost-basis chart formula).

    Source: `nav_history` table written by `build_portfolio_index`. Has known
    quirks (PRU vs yfinance-close discrepancy at inception, PRU averaging
    on reinforces shifts the chart). Will be replaced by `get_nav_from_holdings`
    in Phase D.
    """
    sb = get_client()
    rows = (
        sb.table("nav_history")
        .select("date, nav_value")
        .eq("portfolio_id", portfolio_id)
        .order("date")
        .execute()
        .data
    )
    if not rows:
        return pd.Series(dtype=float)
    return pd.Series(
        {pd.Timestamp(r["date"]): float(r["nav_value"]) for r in rows}
    ).sort_index()


@st.cache_data(ttl=120)
def get_nav_from_holdings(portfolio_id: str) -> pd.Series:
    """[NEW MODEL] Read NAV history from daily_holdings (real fund accounting).

    Sums `value` across all rows (positions + cash) per date, returns a base-100
    series normalized to the T-1 anchor row (where NAV = $initial_capital and
    portfolio holds only cash, pre-investment).

    This is NAV-neutral on rebalances by construction (shares × price + cash$).
    No PRU dependency, no cost-basis artifacts. Audit-friendly: any user can
    `SELECT SUM(value) FROM daily_holdings WHERE portfolio_id=X AND date=Y`
    and reproduce the same number.
    """
    sb = get_client()

    # CRITICAL: paginate. Supabase default limit is 1000 rows. Portfolio_Test
    # has ~3700 rows (138 days × 27 tickers). Without pagination, we'd get
    # only the first 1000 rows with the LAST date partial (some tickers cut
    # off by the limit), creating a fake "NAV drop" on the chart.
    rows = []
    offset = 0
    PAGE = 1000
    while True:
        chunk = (
            sb.table("daily_holdings")
            .select("date, value")
            .eq("portfolio_id", portfolio_id)
            .range(offset, offset + PAGE - 1)
            .execute()
            .data
        )
        if not chunk:
            break
        rows.extend(chunk)
        if len(chunk) < PAGE:
            break
        offset += PAGE

    if not rows:
        return pd.Series(dtype=float)

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df["value"] = df["value"].astype(float)
    nav_per_day = df.groupby("date")["value"].sum().sort_index()
    if nav_per_day.empty:
        return pd.Series(dtype=float)
    base = nav_per_day.iloc[0]  # T-1 anchor = $initial_capital
    if base <= 0:
        return pd.Series(dtype=float)
    return nav_per_day / base * 100


def lazy_write_holdings(portfolio_id: str, positions: list, cash_amount: float,
                        history: pd.DataFrame) -> int:
    """[NEW MODEL] Upsert ONLY today's row in daily_holdings (per ticker + CASH).

    Reads `positions.shares` (current state, post-any-moves) and receives the
    derived `cash_amount` from the caller (see `utils.data.get_cash_amount`).
    Multiplies by today's yfinance close (when available), and upserts one row
    per active ticker plus one CASH row.

    Past days are NEVER touched. If today's close not yet available in yfinance,
    no-op.

    Returns the number of rows upserted (~N+1 if today written, else 0).
    """
    if history.empty or not positions:
        return 0
    from datetime import date as _date
    today = _date.today()
    today_ts = pd.Timestamp(today)
    if today_ts not in history.index:
        return 0

    sb = get_client()
    rows = []
    for p in positions:
        ticker = p.get("ticker")
        shares = float(p.get("shares") or 0)
        if shares <= 0.0001 or not ticker:
            continue
        if ticker not in history.columns:
            continue
        price = history.loc[today_ts, ticker]
        if pd.isna(price):
            continue
        price_f = float(price)
        rows.append({
            "portfolio_id": portfolio_id,
            "date":         today.isoformat(),
            "ticker":       ticker,
            "shares":       round(shares, 8),
            "price":        round(price_f, 4),
            "value":        round(shares * price_f, 2),
        })
    rows.append({
        "portfolio_id": portfolio_id,
        "date":         today.isoformat(),
        "ticker":       "CASH",
        "shares":       round(float(cash_amount or 0), 2),
        "price":        1.0,
        "value":        round(float(cash_amount or 0), 2),
    })

    if rows:
        sb.table("daily_holdings").upsert(
            rows, on_conflict="portfolio_id,date,ticker"
        ).execute()
        get_nav_from_holdings.clear()
    return len(rows)


def lazy_write_nav(portfolio_id: str, positions: list, cash_units: float,
                   history: pd.DataFrame) -> int:
    """Upsert ONLY today's row in nav_history. Past days are NEVER touched.

    Critical invariant (see [[feedback_nav_history_immutable]]):
    nav_history for any `date < today` is IMMUTABLE. Past missing rows must
    be backfilled by an explicit one-shot script using historical state
    (position_snapshots or CSV mirrors) — never by lazy_write, which only
    has access to the CURRENT positions table and would otherwise rewrite
    history with post-move state.

    `cash_units` is accepted for signature compatibility but unused — the
    legacy index ignores cash and starts at base 100 by construction.

    Returns 1 if today's row was written, 0 otherwise.
    """
    if history.empty or not positions:
        return 0

    chart_series = build_portfolio_index(history, positions)
    if chart_series.empty:
        return 0

    from datetime import date as _date
    today = _date.today()
    today_ts = pd.Timestamp(today)

    # Only write today's row if yfinance has data for today.
    # Otherwise, no-op (don't touch yesterday's or any past day's row).
    if today_ts not in chart_series.index:
        return 0
    nav = chart_series.loc[today_ts]
    if pd.isna(nav):
        return 0

    sb = get_client()
    sb.table("nav_history").upsert(
        {
            "portfolio_id": portfolio_id,
            "date":         today.isoformat(),
            "nav_value":    round(float(nav), 6),
        },
        on_conflict="portfolio_id,date",
    ).execute()
    get_nav_series.clear()
    return 1
