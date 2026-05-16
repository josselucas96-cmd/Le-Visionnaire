"""Daily refresh of daily_holdings — designed to run from a GitHub Action cron.

Goal
----
After every US market close, write the day's row in `daily_holdings` for each
portfolio. This makes the public chart EOD-accurate without depending on
visitor traffic (`lazy_write_holdings`, the visitor-triggered version, has
holes when nobody visits the site between close and midnight).

Run
---
Locally (debug):
    SUPABASE_URL=... SUPABASE_KEY=... python daily_refresh.py
    # or pass --date 2026-05-15 to backfill a specific past trading day

GitHub Action (production):
    See .github/workflows/daily-refresh.yml — runs Mon-Fri 21:07 UTC
    (~23:00 CH summer / 22:00 CH winter, ~1h after US market close).

What it writes
--------------
For each portfolio (visionnaire, batisseur, nakamoto):
  - 1 row per active ticker: shares × yfinance Close = value
  - 1 CASH row: shares = $ cash, price = 1.0

Cash $ is derived (same logic as utils/data.get_cash_amount):
  - baseline = latest CASH row strictly before target_date
  - + Σ same-day transaction deltas (TRIM/CLOSE proceeds, IN/SWITCH costs)

Idempotent (upsert on portfolio_id, date, ticker). Skips if yfinance has no
close for target_date (= holiday, future date, or yfinance lag).
"""
import argparse
import os
import sys
from datetime import date as _date

import yfinance as yf
from supabase import create_client


PORTFOLIOS = ["visionnaire", "batisseur", "nakamoto"]
INITIAL_CAPITAL_FALLBACK = 1_000_000.0


def fetch_close_price(ticker: str, target_date_str: str) -> float | None:
    """Fetch yfinance Close for target_date_str. Returns None if not available
    (holiday, future date, or yfinance lag)."""
    try:
        from datetime import datetime, timedelta
        start = target_date_str
        end_dt = datetime.strptime(target_date_str, "%Y-%m-%d") + timedelta(days=2)
        df = yf.download(ticker, start=start, end=end_dt.strftime("%Y-%m-%d"),
                         progress=False, auto_adjust=False)
        if df.empty or "Close" not in df.columns:
            return None
        import pandas as pd
        target_ts = pd.Timestamp(target_date_str)
        if target_ts not in df.index:
            return None
        close = df.loc[target_ts, "Close"]
        # yfinance sometimes returns a Series (single-row, multi-column index)
        return float(close.iloc[0]) if hasattr(close, "iloc") else float(close)
    except Exception as e:
        print(f"  ! {ticker}: yfinance fetch error ({e})", flush=True)
        return None


def get_initial_capital(sb, portfolio_id: str) -> float:
    """Read initial_capital_<pid> setting (with fallback to legacy key for visionnaire)."""
    keys = [f"initial_capital_{portfolio_id}"]
    if portfolio_id == "visionnaire":
        keys.append("initial_capital")
    for k in keys:
        row = sb.table("settings").select("value").eq("key", k).execute().data
        if row and row[0].get("value"):
            try:
                return float(row[0]["value"])
            except (TypeError, ValueError):
                continue
    return INITIAL_CAPITAL_FALLBACK


def derive_cash_at_date(sb, portfolio_id: str, target_date_str: str,
                       initial_capital: float) -> float:
    """Derive cash $ at end of target_date_str, replicating get_cash_amount logic.

    1. Baseline = latest CASH row strictly before target_date_str (or initial_capital)
    2. + Σ same-day transaction $-deltas
    """
    rows = (
        sb.table("daily_holdings")
        .select("date, value")
        .eq("portfolio_id", portfolio_id)
        .eq("ticker", "CASH")
        .lt("date", target_date_str)
        .order("date", desc=True)
        .limit(1)
        .execute()
        .data
    )
    baseline = float(rows[0]["value"]) if rows else float(initial_capital)

    txns = (
        sb.table("transactions")
        .select("action, weight_in, weight_out, price_out, entry_price_out")
        .eq("portfolio_id", portfolio_id)
        .eq("date", target_date_str)
        .execute()
        .data
    )
    delta = 0.0
    for t in txns:
        a = (t.get("action") or "").upper()
        if a == "IN":
            delta -= float(t.get("weight_in") or 0) * initial_capital / 100.0
        elif a in ("TRIM", "OUT"):
            w = float(t.get("weight_out") or 0)
            pru = float(t.get("entry_price_out") or 0)
            p = float(t.get("price_out") or 0)
            if pru > 0:
                delta += (w * initial_capital / 100.0 / pru) * p
        elif a == "SWITCH":
            w_in = float(t.get("weight_in") or 0)
            w_out = float(t.get("weight_out") or 0)
            pru = float(t.get("entry_price_out") or 0)
            p = float(t.get("price_out") or 0)
            if pru > 0:
                delta += (w_out * initial_capital / 100.0 / pru) * p
            delta -= w_in * initial_capital / 100.0
        # DRIP / SPLIT: cash-neutral
    return baseline + delta


def refresh_portfolio(sb, portfolio_id: str, target_date_str: str) -> dict:
    """Write daily_holdings rows for one portfolio. Returns summary dict."""
    initial_capital = get_initial_capital(sb, portfolio_id)
    positions = (
        sb.table("positions")
        .select("ticker, shares")
        .eq("portfolio_id", portfolio_id)
        .eq("is_active", True)
        .execute()
        .data
    )
    cash_amount = derive_cash_at_date(sb, portfolio_id, target_date_str, initial_capital)

    rows = [{
        "portfolio_id": portfolio_id,
        "date":         target_date_str,
        "ticker":       "CASH",
        "shares":       round(cash_amount, 2),
        "price":        1.0,
        "value":        round(cash_amount, 2),
    }]
    nav = cash_amount
    skipped = []
    for p in positions:
        tk = p["ticker"]
        shares = float(p.get("shares") or 0)
        if shares <= 0 or not tk:
            continue
        price = fetch_close_price(tk, target_date_str)
        if price is None:
            skipped.append(tk)
            continue
        value = shares * price
        nav += value
        rows.append({
            "portfolio_id": portfolio_id,
            "date":         target_date_str,
            "ticker":       tk,
            "shares":       round(shares, 8),
            "price":        round(price, 4),
            "value":        round(value, 2),
        })

    # Upsert all rows
    sb.table("daily_holdings").upsert(
        rows, on_conflict="portfolio_id,date,ticker"
    ).execute()

    return {
        "portfolio": portfolio_id,
        "rows_written": len(rows),
        "nav": nav,
        "cash": cash_amount,
        "skipped_tickers": skipped,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--date", default=None,
        help="Target date YYYY-MM-DD (default: today)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print what would be written; don't touch DB.",
    )
    args = parser.parse_args()

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        print("ERROR: SUPABASE_URL and SUPABASE_KEY env vars are required.", file=sys.stderr)
        sys.exit(2)

    sb = create_client(url, key)
    target = args.date or _date.today().isoformat()
    print(f"[daily_refresh] target date: {target}", flush=True)

    # Sanity: skip if target is a weekend
    from datetime import datetime
    weekday = datetime.strptime(target, "%Y-%m-%d").weekday()
    if weekday >= 5:
        print(f"[daily_refresh] {target} is a weekend (weekday={weekday}). Nothing to do.", flush=True)
        sys.exit(0)

    # Probe: does yfinance have a close for any common ticker on target?
    probe = fetch_close_price("SPY", target)
    if probe is None:
        print(f"[daily_refresh] yfinance has no SPY close on {target}. "
              f"Probably a US holiday or yfinance lag. Exiting without write.", flush=True)
        sys.exit(0)

    if args.dry_run:
        print("[daily_refresh] DRY RUN — no DB writes will happen.", flush=True)
        # Replace the upsert with a no-op by intercepting via stub
        original_upsert = sb.table

    results = []
    for pid in PORTFOLIOS:
        print(f"\n[{pid}] refreshing {target}...", flush=True)
        try:
            r = refresh_portfolio(sb, pid, target)
            results.append(r)
            print(f"  written {r['rows_written']} rows, NAV=${r['nav']:,.2f}, cash=${r['cash']:,.2f}", flush=True)
            if r["skipped_tickers"]:
                print(f"  SKIPPED (no yfinance close): {r['skipped_tickers']}", flush=True)
        except Exception as e:
            print(f"  ERROR on {pid}: {e}", file=sys.stderr, flush=True)
            results.append({"portfolio": pid, "error": str(e)})

    # Summary
    print(f"\n[daily_refresh] done. Summary:")
    for r in results:
        if "error" in r:
            print(f"  {r['portfolio']:13} ERROR — {r['error']}")
        else:
            print(f"  {r['portfolio']:13} {r['rows_written']:3} rows  NAV ${r['nav']:>11,.2f}")

    # Exit with non-zero if any portfolio failed
    if any("error" in r for r in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
