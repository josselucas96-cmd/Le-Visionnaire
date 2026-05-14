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
    """Read NAV history for this portfolio as a date-indexed Series."""
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
