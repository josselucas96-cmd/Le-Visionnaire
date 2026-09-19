"""NAV snapshot persistence — daily portfolio value frozen in DB.

WRITES happen in the nightly cron only (daily_refresh.py → daily_holdings).
This module is read-side for the app. The visitor-triggered writers
(lazy_write_holdings / lazy_write_nav) were removed on 2026-09-19: they could
never fire (yf.download `end` is exclusive, so "today" was never in the
history index) and a working version would have frozen intraday quotes into
immutable rows. See memory project_pipeline_hardening.

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
    #
    # CRITICAL #2: the pagination MUST have a stable, total sort order, else
    # PostgREST's implicit ordering can differ between page requests and rows
    # near the 1000-row boundary get returned on BOTH pages → double-counted →
    # a phantom NAV *spike* on the boundary dates (once a portfolio grows past
    # 1000 rows). (portfolio_id, date, ticker) is the unique upsert key, so
    # ordering by (date, ticker) is a stable total order within a portfolio.
    rows = []
    offset = 0
    PAGE = 1000
    while True:
        chunk = (
            sb.table("daily_holdings")
            .select("date, value")
            .eq("portfolio_id", portfolio_id)
            .order("date").order("ticker")
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


