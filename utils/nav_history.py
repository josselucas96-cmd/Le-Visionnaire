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
    """Fill missing NAV rows + always refresh the latest day.

    First call (empty table): backfills inception → today by computing the
    legacy buy-and-hold index with current positions.

    Routine call:
    - Past days already in DB are FROZEN — never recomputed (immutability).
    - The latest day in `chart_series` is upserted so post-move state is
      reflected within the same trading day. As soon as the next trading
      day arrives, today becomes "past" and freezes.

    `cash_units` is accepted for signature compatibility but unused — the
    legacy index ignores cash and starts at base 100 by construction.

    Returns the number of rows written (insert + upsert).
    """
    if history.empty or not positions:
        return 0

    chart_series = build_portfolio_index(history, positions)
    if chart_series.empty:
        return 0

    sb = get_client()
    existing = (
        sb.table("nav_history")
        .select("date")
        .eq("portfolio_id", portfolio_id)
        .execute()
        .data
    )
    existing_dates = {r["date"] for r in existing}

    latest_ts   = chart_series.index[-1]
    latest_date = latest_ts.date().isoformat()
    latest_nav  = chart_series.iloc[-1]

    rows_to_insert = []
    for ts, nav in chart_series.items():
        date_str = ts.date().isoformat()
        if pd.isna(nav):
            continue
        if date_str == latest_date:
            continue  # latest is upserted below
        if date_str in existing_dates:
            continue
        rows_to_insert.append({
            "portfolio_id": portfolio_id,
            "date":         date_str,
            "nav_value":    round(float(nav), 6),
        })

    written = 0
    if rows_to_insert:
        CHUNK = 100
        for i in range(0, len(rows_to_insert), CHUNK):
            sb.table("nav_history").insert(rows_to_insert[i:i + CHUNK]).execute()
        written += len(rows_to_insert)

    if pd.notna(latest_nav):
        sb.table("nav_history").upsert(
            {
                "portfolio_id": portfolio_id,
                "date":         latest_date,
                "nav_value":    round(float(latest_nav), 6),
            },
            on_conflict="portfolio_id,date",
        ).execute()
        written += 1

    if written:
        get_nav_series.clear()
    return written
