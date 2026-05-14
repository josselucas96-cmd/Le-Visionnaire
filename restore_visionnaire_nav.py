"""One-shot: restore Visionnaire's nav_history using the inception snapshot.

Reads snapshots/visionnaire/2026-04-13.csv (state at launch, pre-moves).
Computes NAV for each trading day from inception to yesterday, using the
INITIAL weights/PRUs (not the current post-move state). Upserts into
nav_history. Today's row is NOT touched — let lazy_write_nav handle it
on the next page visit, using post-move state.

This is the only sanctioned way to "fix" a corrupted nav_history: explicit
state from a historical snapshot, never wipe + recompute with current state.
"""
import csv
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import toml
import yfinance as yf
from supabase import create_client


PORTFOLIO_ID = "visionnaire"
INCEPTION    = "2026-04-13"


def load_initial_state():
    csv_path = Path(__file__).parent / "snapshots" / PORTFOLIO_ID / f"{INCEPTION}.csv"
    rows = []
    with open(csv_path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append({
                "ticker":      r["ticker"],
                "weight":      float(r["weight"]),
                "entry_price": float(r["entry_price"]),
                "entry_date":  INCEPTION,
            })
    return rows


def fetch_history(tickers):
    end = (date.today() + timedelta(days=1)).isoformat()
    df = yf.download(list(tickers), start=INCEPTION, end=end,
                     auto_adjust=True, progress=False)
    if df.empty:
        return df
    if isinstance(df.columns, pd.MultiIndex):
        df = df["Close"]
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    df.index = pd.to_datetime(df.index.date)
    return df


def build_portfolio_series(positions, history):
    """Re-implements build_portfolio_index logic (chart base = entry_price)."""
    if history.empty or not positions:
        return pd.Series(dtype=float)
    total_w = sum(p["weight"] for p in positions)
    if total_w == 0:
        return pd.Series(dtype=float)

    portfolio = pd.Series(0.0, index=history.index)
    contributed = False
    for p in positions:
        ticker = p["ticker"]
        if ticker not in history.columns:
            continue
        w = p["weight"] / total_w
        series = history[ticker].dropna()
        if series.empty:
            continue
        entry_dt = pd.Timestamp(p["entry_date"])
        after = series[series.index >= entry_dt]
        if after.empty:
            continue
        base = float(p["entry_price"])
        if base <= 0:
            base = float(after.iloc[0])
        normalized_after = after / base * 100
        before_idx = series.index[series.index < entry_dt]
        normalized_before = pd.Series(100.0, index=before_idx)
        full = pd.concat([normalized_before, normalized_after])
        full = full.reindex(history.index).ffill().bfill()
        portfolio += full * w
        contributed = True
    return portfolio if contributed else pd.Series(dtype=float)


def main():
    secrets = toml.load(Path(__file__).parent / ".streamlit" / "secrets.toml")
    sb = create_client(secrets["supabase_url"], secrets["supabase_key"])

    positions = load_initial_state()
    print(f"Initial state: {len(positions)} positions @ inception {INCEPTION}")

    tickers = tuple(p["ticker"] for p in positions)
    history = fetch_history(tickers)
    if history.empty:
        print("ERROR: yfinance returned empty history")
        return
    print(f"Fetched yfinance history: {history.shape[0]} trading days")

    series = build_portfolio_series(positions, history)
    if series.empty:
        print("ERROR: portfolio series empty")
        return
    print(f"Computed NAV series: {len(series)} days, range [{series.min():.2f}, {series.max():.2f}]")

    today_str = date.today().isoformat()
    rows = []
    for ts, nav in series.items():
        if pd.isna(nav):
            continue
        date_str = ts.date().isoformat()
        # Skip today — let lazy_write_nav write it on next page visit with post-move state
        if date_str >= today_str:
            continue
        rows.append({
            "portfolio_id": PORTFOLIO_ID,
            "date":         date_str,
            "nav_value":    round(float(nav), 6),
        })

    if not rows:
        print("Nothing to upsert (no past days computed)")
        return

    # Preview
    print(f"\nWill upsert {len(rows)} rows. First/last:")
    print(f"  {rows[0]}")
    print(f"  {rows[-1]}")
    answer = input("\nApply? [y/N]: ").strip().lower()
    if answer != "y":
        print("Aborted.")
        return

    CHUNK = 100
    for i in range(0, len(rows), CHUNK):
        sb.table("nav_history").upsert(
            rows[i:i + CHUNK], on_conflict="portfolio_id,date"
        ).execute()
    print(f"\nDone. {len(rows)} rows upserted into nav_history for {PORTFOLIO_ID}.")


if __name__ == "__main__":
    main()
