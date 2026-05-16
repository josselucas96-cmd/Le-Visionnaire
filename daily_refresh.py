"""Daily refresh of daily_holdings — designed to run from a GitHub Action cron.

Goal
----
After every US market close (or on weekends/holidays), write the day's row
in `daily_holdings` for each portfolio. This makes the public chart EOD-
accurate without depending on visitor traffic (`lazy_write_holdings`, the
visitor-triggered version, has holes when nobody visits the site between
close and midnight).

Runs 7/7 since 2026-05-16. Weekend/holiday rationale: the Nakamoto
benchmark is Bitcoin (24/7). On Sat/Sun, the BTC line extends past the
portfolio line, creating a visual disconnect. By writing weekend rows
that propagate the latest equity close, the portfolio line aligns
timewise with Bitcoin (flat over the weekend, since equities don't move).
Visionnaire/Bâtisseur are unaffected (their benchmarks are 5/7 too).

Run
---
Locally (debug):
    SUPABASE_URL=... SUPABASE_KEY=... python daily_refresh.py
    # or pass --date 2026-05-15 to backfill a specific past day

GitHub Action (production):
    See .github/workflows/daily-refresh.yml — runs daily 22:07 UTC
    (~23-00:00 CH, ~1-2h after US market close on weekdays).

What it writes
--------------
For each portfolio (visionnaire, batisseur, nakamoto):
  - 1 row per active ticker: shares × latest_close ≤ target_date = value
  - 1 CASH row: shares = $ cash, price = 1.0

On weekend/holiday: yfinance has no Close for target_date, so we fall
back to the latest available close ≤ target_date (= previous trading
day). Shares and cash are still derived from the CURRENT positions/
transactions (reflects any moves committed at any time of day).

Cash $ is derived (same logic as utils/data.get_cash_amount):
  - baseline = latest CASH row strictly before target_date
  - + Σ same-day transaction deltas (TRIM/CLOSE proceeds, IN/SWITCH costs)

Idempotent (upsert on portfolio_id, date, ticker).
"""
import argparse
import os
import sys
from datetime import date as _date

import yfinance as yf
from supabase import create_client


PORTFOLIOS = ["visionnaire", "batisseur", "nakamoto"]
INITIAL_CAPITAL_FALLBACK = 1_000_000.0


def fetch_close_price(ticker: str, target_date_str: str) -> tuple[float | None, str | None]:
    """Fetch the latest Close ≤ target_date_str.

    On a trading day: returns the close for that day.
    On weekend/holiday: returns the close from the most recent trading day
    before target_date_str (so equity tickers carry forward Friday's close
    into Sat/Sun rows).

    Returns (price, actual_close_date_str) or (None, None) if no data found.
    """
    try:
        from datetime import datetime, timedelta
        import pandas as pd

        # Fetch a 10-day window ending at target_date to find the latest available
        target = datetime.strptime(target_date_str, "%Y-%m-%d")
        start = (target - timedelta(days=10)).strftime("%Y-%m-%d")
        end = (target + timedelta(days=1)).strftime("%Y-%m-%d")
        df = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=False)
        if df.empty or "Close" not in df.columns:
            return None, None

        # Keep only rows with date ≤ target_date_str
        df = df[df.index <= pd.Timestamp(target_date_str)]
        if df.empty:
            return None, None

        last_idx = df.index[-1]
        close = df.loc[last_idx, "Close"]
        price = float(close.iloc[0]) if hasattr(close, "iloc") else float(close)
        return price, last_idx.strftime("%Y-%m-%d")
    except Exception as e:
        print(f"  ! {ticker}: yfinance fetch error ({e})", flush=True)
        return None, None


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
    propagated = []  # tickers where price comes from a date before target
    for p in positions:
        tk = p["ticker"]
        shares = float(p.get("shares") or 0)
        if shares <= 0 or not tk:
            continue
        price, actual_date = fetch_close_price(tk, target_date_str)
        if price is None:
            skipped.append(tk)
            continue
        if actual_date != target_date_str:
            propagated.append((tk, actual_date))
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
        "propagated": propagated,
    }


def refresh_current_prices(sb) -> dict:
    """Upsert latest price + metadata per unique ticker into `current_prices`.

    Why: visitor pages currently call yfinance directly (1 call per ticker
    × N visitors / cache_TTL). With this table populated nightly, the site
    can read prices from Supabase in 1 query — eliminating Yahoo rate-limit
    risk and dropping page load from ~30s to ~2s.

    Uses fast_info (same source as utils/market.get_prices). During off-hours
    (when this cron runs) fast_info returns the last close.

    Schema: ticker PK + price, change_pct, market_cap, currency, fetched_at.
    """
    # Gather all unique tickers across active positions in all portfolios
    all_tickers: set[str] = set()
    for pid in PORTFOLIOS:
        rows = (
            sb.table("positions").select("ticker")
            .eq("portfolio_id", pid).eq("is_active", True)
            .execute().data
        )
        for r in rows:
            tk = r.get("ticker")
            if tk:
                all_tickers.add(tk)

    print(f"\n[current_prices] refreshing {len(all_tickers)} unique tickers...", flush=True)

    payload = []
    failed = []
    now_iso = None
    from datetime import datetime, timezone
    now_iso = datetime.now(timezone.utc).isoformat()

    for tk in sorted(all_tickers):
        try:
            info = yf.Ticker(tk).fast_info
            price = info.last_price
            prev = info.previous_close
            if price is None or prev is None:
                failed.append(tk)
                continue
            mc = getattr(info, "market_cap", None)
            ccy = getattr(info, "currency", None) or "USD"
            payload.append({
                "ticker":     tk,
                "price":      round(float(price), 4),
                "change_pct": round((float(price) - float(prev)) / float(prev) * 100, 4) if prev else None,
                "market_cap": float(mc) if mc is not None else None,
                "currency":   ccy,
                "fetched_at": now_iso,
            })
        except Exception as e:
            print(f"  ! {tk}: fast_info error ({e})", flush=True)
            failed.append(tk)

    if payload:
        sb.table("current_prices").upsert(payload, on_conflict="ticker").execute()
        print(f"[current_prices] upserted {len(payload)} rows.", flush=True)
    if failed:
        print(f"[current_prices] FAILED to fetch: {failed}", flush=True)

    return {"ok": len(payload), "failed": failed}


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

    # Probe: can we find any close ≤ target for SPY? (sanity check for very
    # early dates or yfinance being totally down).
    probe_price, probe_date = fetch_close_price("SPY", target)
    if probe_price is None:
        print(f"[daily_refresh] yfinance has no SPY close at all near {target}. "
              f"Likely yfinance is down or target is before 1993. Exiting.", flush=True)
        sys.exit(0)
    if probe_date != target:
        from datetime import datetime
        weekday = datetime.strptime(target, "%Y-%m-%d").weekday()
        label = "weekend" if weekday >= 5 else "US holiday or pre-market"
        print(f"[daily_refresh] {target} is not a trading day ({label}). "
              f"Will propagate the latest close from {probe_date} for all equity tickers.", flush=True)

    if args.dry_run:
        print("[daily_refresh] DRY RUN — no DB writes will happen.", flush=True)

    results = []
    for pid in PORTFOLIOS:
        print(f"\n[{pid}] refreshing {target}...", flush=True)
        try:
            r = refresh_portfolio(sb, pid, target)
            results.append(r)
            print(f"  written {r['rows_written']} rows, NAV=${r['nav']:,.2f}, cash=${r['cash']:,.2f}", flush=True)
            if r.get("propagated"):
                propagated_str = ", ".join(f"{t}<-{d}" for t, d in r["propagated"][:3])
                more = f" (+{len(r['propagated'])-3} more)" if len(r["propagated"]) > 3 else ""
                print(f"  PROPAGATED prices (target was non-trading day): {propagated_str}{more}", flush=True)
            if r["skipped_tickers"]:
                print(f"  SKIPPED (no yfinance data found): {r['skipped_tickers']}", flush=True)
        except Exception as e:
            print(f"  ERROR on {pid}: {e}", file=sys.stderr, flush=True)
            results.append({"portfolio": pid, "error": str(e)})

    # Refresh current_prices (latest price/metadata per ticker, for frontend)
    try:
        cp_result = refresh_current_prices(sb)
    except Exception as e:
        print(f"\n[current_prices] refresh failed: {e}", file=sys.stderr, flush=True)
        cp_result = {"ok": 0, "failed": ["(crashed)"]}

    # Summary
    print(f"\n[daily_refresh] done. Summary:")
    for r in results:
        if "error" in r:
            print(f"  {r['portfolio']:13} ERROR — {r['error']}")
        else:
            print(f"  {r['portfolio']:13} {r['rows_written']:3} rows  NAV ${r['nav']:>11,.2f}")
    failed_n = len(cp_result.get("failed", []))
    failed_suffix = f" ({failed_n} failed)" if failed_n else ""
    print(f"  current_prices  {cp_result['ok']:3} tickers updated{failed_suffix}")

    # Exit with non-zero if any portfolio failed
    if any("error" in r for r in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
