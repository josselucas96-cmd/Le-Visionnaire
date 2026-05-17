"""One-shot: migrate Portfolio_Test inception from 2026-05-16 to 2026-01-01.

What this does:
1. Verifies test portfolio has inception_date='2026-01-01' (set via SQL beforehand)
2. Wipes existing test data: positions, transactions, daily_holdings (test only),
   dividend_factors entries with old entry_date='2026-05-16', old CSV snapshot
3. Fetches yfinance close on 2025-12-31 for the 26 source tickers (Bâtisseur)
4. Inserts 26 new positions with entry_date=2026-01-01, fresh PRU
5. Inserts 26 IN transactions dated 2026-01-01
6. Inserts T-1 anchor (2025-12-31, CASH, $1M)
7. BACKFILLS daily_holdings for every day from 2026-01-01 to 2026-05-16:
   - 26 ticker rows per day (shares × latest close ≤ day, propagating weekends/holidays)
   - 1 CASH row per day = $55K (no moves between inception and today)
8. Regenerates CSV snapshot at snapshots/test/2026-01-01.csv

yfinance call count: 1 yf.download per ticker for the full historical range
(~26 calls), plus a probe for 2025-12-31 close. ~30-60 seconds total.

Safety:
- Refuses to run if inception_date is NOT '2026-01-01' (you'd need to SQL it first)
- Dry-run preview before writes
- Idempotent on subsequent runs (wipes + rebuilds)

After running:
- Run `python daily_refresh.py` (or wait for cron) to refresh dividend_factors
  for the new (ticker, 2026-01-01) pairs
- Reload Admin cockpit → Portfolio_Test should show 4.5 months of chart history
"""
import csv
import sys
from datetime import date as _date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import toml
import yfinance as yf
from supabase import create_client


TEST_PID         = "test"
INITIAL_CAPITAL  = 1_000_000.0
NEW_INCEPTION    = "2026-01-01"
NEW_T_MINUS_1    = "2025-12-31"
OLD_INCEPTION    = "2026-05-16"
SOURCE_PID       = "batisseur"
TODAY            = _date.today().isoformat()  # 2026-05-16


def fetch_close_history(ticker: str, start: str, end: str) -> pd.Series | None:
    """Single yf.download for the full historical range. Returns Close series
    indexed by date (timezone-stripped), or None on failure."""
    try:
        df = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=False)
        if df.empty or "Close" not in df.columns:
            return None
        s = df["Close"]
        if isinstance(s, pd.DataFrame):
            s = s.iloc[:, 0]
        if s.index.tz is not None:
            s.index = s.index.tz_localize(None)
        return s.dropna()
    except Exception as e:
        print(f"  ! {ticker}: yfinance error ({e})")
        return None


def latest_close_le(series: pd.Series, target_date: str) -> float | None:
    """Return Close from series for the latest date <= target_date."""
    if series is None or series.empty:
        return None
    s = series[series.index <= pd.Timestamp(target_date)]
    if s.empty:
        return None
    return float(s.iloc[-1])


def main():
    secrets = toml.load(Path(__file__).parent / ".streamlit" / "secrets.toml")
    sb = create_client(secrets["supabase_url"], secrets["supabase_key"])

    # SAFETY 1: portfolio exists with new inception
    pf = sb.table("portfolios").select("*").eq("id", TEST_PID).execute().data
    if not pf:
        print(f"ABORT: portfolio '{TEST_PID}' not found.")
        sys.exit(1)
    pf = pf[0]
    if pf.get("inception_date") != NEW_INCEPTION:
        print(f"ABORT: portfolio '{TEST_PID}' inception_date is '{pf.get('inception_date')}', expected '{NEW_INCEPTION}'.")
        print(f"Run this SQL first:")
        print(f"  UPDATE public.portfolios SET inception_date = '{NEW_INCEPTION}' WHERE id = '{TEST_PID}';")
        sys.exit(1)
    print(f"OK: portfolio '{TEST_PID}' has inception_date={NEW_INCEPTION}")

    # SAFETY 2: source must exist
    src = sb.table("positions").select("*").eq("portfolio_id", SOURCE_PID).eq("is_active", True).execute().data
    if not src:
        print(f"ABORT: source portfolio '{SOURCE_PID}' has no active positions.")
        sys.exit(1)
    print(f"OK: source portfolio '{SOURCE_PID}' has {len(src)} positions")

    # FETCH historical close for each source ticker
    fetch_start = NEW_T_MINUS_1
    fetch_end = (datetime.strptime(TODAY, "%Y-%m-%d") + timedelta(days=2)).strftime("%Y-%m-%d")
    print(f"\nFetching yfinance close history [{fetch_start}, {fetch_end}) for {len(src)} tickers...")
    closes_by_ticker: dict[str, pd.Series] = {}
    failed = []
    for sp in src:
        tk = sp["ticker"]
        s = fetch_close_history(tk, fetch_start, fetch_end)
        if s is None or s.empty:
            failed.append(tk)
            continue
        closes_by_ticker[tk] = s

    if failed:
        print(f"WARNING: failed to fetch {len(failed)} tickers: {failed}")
        print(f"They will be skipped. Verify and re-run if needed.")

    # Build new positions with PRU = close 2025-12-31
    new_positions = []
    for sp in src:
        tk = sp["ticker"]
        if tk not in closes_by_ticker:
            continue
        entry_price = latest_close_le(closes_by_ticker[tk], NEW_T_MINUS_1)
        if entry_price is None or entry_price <= 0:
            print(f"  ! {tk}: no close <= {NEW_T_MINUS_1}, skipping")
            continue
        weight = float(sp["weight"])
        cost = weight * INITIAL_CAPITAL / 100.0
        shares = round(cost / entry_price, 8)
        units = round(weight / entry_price, 8)
        new_positions.append({
            "portfolio_id":            TEST_PID,
            "ticker":                  tk,
            "name":                    sp.get("name"),
            "isin":                    sp.get("isin"),
            "layer":                   sp.get("layer"),
            "weight":                  weight,
            "units":                   units,
            "shares":                  shares,
            "entry_price":             round(entry_price, 4),
            "entry_date":              NEW_INCEPTION,
            "is_active":               True,
            "sector":                  sp.get("sector"),
            "geography":               sp.get("geography"),
            "thematic":                sp.get("thematic"),
            "thesis_short":            sp.get("thesis_short"),
            "expected_revenue_growth": sp.get("expected_revenue_growth"),
            "expected_gross_margin":   sp.get("expected_gross_margin"),
            "expected_op_margin":      sp.get("expected_op_margin"),
            "expected_fcf_margin":     sp.get("expected_fcf_margin"),
        })

    total_weight = sum(p["weight"] for p in new_positions)
    cash_pct = 100.0 - total_weight
    cash_dollars = round(INITIAL_CAPITAL * cash_pct / 100.0, 2)

    # Count days to backfill
    start_dt = datetime.strptime(NEW_INCEPTION, "%Y-%m-%d").date()
    end_dt = _date.fromisoformat(TODAY)
    n_days = (end_dt - start_dt).days  # excludes today (cron handles it)

    # DRY-RUN
    print("\n" + "=" * 70)
    print(f"DRY RUN -- migration of '{TEST_PID}' to inception {NEW_INCEPTION}:")
    print("=" * 70)
    print(f"\nWIPE existing test data:")
    n_old_pos = len(sb.table("positions").select("id").eq("portfolio_id", TEST_PID).execute().data)
    n_old_txn = len(sb.table("transactions").select("id").eq("portfolio_id", TEST_PID).execute().data)
    n_old_dh  = len(sb.table("daily_holdings").select("date", count="exact").eq("portfolio_id", TEST_PID).execute().data)
    print(f"  [positions]       {n_old_pos} rows")
    print(f"  [transactions]    {n_old_txn} rows")
    print(f"  [daily_holdings]  {n_old_dh} rows")
    print(f"  [dividend_factors] all rows with entry_date={OLD_INCEPTION} for these tickers")
    print(f"\nINSERT new data:")
    print(f"  [positions]       {len(new_positions)} rows (PRU = close {NEW_T_MINUS_1})")
    print(f"    Sum weight: {total_weight:.2f}%  ->  cash: {cash_pct:.2f}% = ${cash_dollars:,.2f}")
    print(f"  [transactions]    {len(new_positions)} IN rows dated {NEW_INCEPTION}")
    print(f"  [daily_holdings]  T-1 anchor (1 row) + {n_days} days of backfill = ~{1 + n_days * (len(new_positions) + 1)} rows total")
    print(f"  [CSV] snapshots/{TEST_PID}/{NEW_INCEPTION}.csv (recovery mirror)")
    print()

    answer = input("Apply? [y/N]: ").strip().lower()
    if answer != "y":
        print("Aborted.")
        sys.exit(0)

    # === APPLY ===
    print("\nApplying...")

    # 1. WIPE
    print("\n[1/7] Wiping old test data...")
    sb.table("transactions").delete().eq("portfolio_id", TEST_PID).execute()
    sb.table("daily_holdings").delete().eq("portfolio_id", TEST_PID).execute()
    sb.table("positions").delete().eq("portfolio_id", TEST_PID).execute()
    # Clean stale dividend_factors entries (only those that match deleted positions)
    sb.table("dividend_factors").delete().eq("entry_date", OLD_INCEPTION).execute()
    # Delete old CSV if exists
    old_csv = Path(__file__).parent / "snapshots" / TEST_PID / f"{OLD_INCEPTION}.csv"
    if old_csv.exists():
        old_csv.unlink()
    print(f"  OK — {n_old_pos} positions, {n_old_txn} txns, {n_old_dh} daily_holdings deleted")

    # 2. INSERT positions
    print("\n[2/7] Inserting new positions...")
    sb.table("positions").insert(new_positions).execute()
    print(f"  OK — {len(new_positions)} positions inserted")

    # 3. INSERT IN transactions
    print("\n[3/7] Inserting IN transactions...")
    now_iso = datetime.now(timezone.utc).isoformat()
    txns = [{
        "portfolio_id": TEST_PID,
        "date":         NEW_INCEPTION,
        "action":       "IN",
        "ticker_in":    p["ticker"],
        "price_in":     p["entry_price"],
        "weight_in":    p["weight"],
        "reason":       "New position (Portfolio_Test re-inception 2026-01-01)",
        "executed_at":  now_iso,
    } for p in new_positions]
    sb.table("transactions").insert(txns).execute()
    print(f"  OK — {len(txns)} IN transactions inserted")

    # 4. T-1 anchor
    print("\n[4/7] Writing T-1 anchor...")
    sb.table("daily_holdings").upsert([{
        "portfolio_id": TEST_PID,
        "date":         NEW_T_MINUS_1,
        "ticker":       "CASH",
        "shares":       INITIAL_CAPITAL,
        "price":        1.0,
        "value":        INITIAL_CAPITAL,
    }], on_conflict="portfolio_id,date,ticker").execute()
    print(f"  OK — T-1 anchor at {NEW_T_MINUS_1}: CASH=${INITIAL_CAPITAL:,.0f}")

    # 5. BACKFILL daily_holdings for every day from NEW_INCEPTION to TODAY (exclusive)
    print(f"\n[5/7] Backfilling daily_holdings from {NEW_INCEPTION} to {TODAY} (~{n_days} days)...")
    rows_to_upsert = []
    cur = start_dt
    while cur <= end_dt:
        d_str = cur.isoformat()
        # CASH row (constant $55K, no moves)
        rows_to_upsert.append({
            "portfolio_id": TEST_PID,
            "date":         d_str,
            "ticker":       "CASH",
            "shares":       round(cash_dollars, 2),
            "price":        1.0,
            "value":        round(cash_dollars, 2),
        })
        # Equity rows
        for p in new_positions:
            tk = p["ticker"]
            shares = float(p["shares"])
            close = latest_close_le(closes_by_ticker[tk], d_str)
            if close is None:
                continue  # before data starts (shouldn't happen post NEW_INCEPTION)
            value = shares * close
            rows_to_upsert.append({
                "portfolio_id": TEST_PID,
                "date":         d_str,
                "ticker":       tk,
                "shares":       round(shares, 8),
                "price":        round(close, 4),
                "value":        round(value, 2),
            })
        cur += timedelta(days=1)

    # Batch upsert (Supabase supports up to ~1000 rows per call, be safe with 500)
    BATCH = 500
    print(f"  Total rows to write: {len(rows_to_upsert)} (in batches of {BATCH})")
    for i in range(0, len(rows_to_upsert), BATCH):
        batch = rows_to_upsert[i:i + BATCH]
        sb.table("daily_holdings").upsert(batch, on_conflict="portfolio_id,date,ticker").execute()
        print(f"    Batch {i // BATCH + 1}: {len(batch)} rows upserted")

    # 6. CSV snapshot
    print(f"\n[6/7] Writing CSV snapshot...")
    snap_dir = Path(__file__).parent / "snapshots" / TEST_PID
    snap_dir.mkdir(parents=True, exist_ok=True)
    snap_path = snap_dir / f"{NEW_INCEPTION}.csv"
    with open(snap_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["ticker", "weight", "units", "entry_price", "snapshot_type"])
        w.writeheader()
        for p in new_positions:
            w.writerow({
                "ticker":        p["ticker"],
                "weight":        p["weight"],
                "units":         f"{p['units']:.8f}",
                "entry_price":   p["entry_price"],
                "snapshot_type": "initial",
            })
    print(f"  OK — {snap_path}")

    # 7. Verify final state
    print(f"\n[7/7] Verification:")
    dates = sorted(set(r["date"] for r in sb.table("daily_holdings").select("date").eq("portfolio_id", TEST_PID).execute().data))
    last_date = dates[-1]
    last_nav = sum(float(r["value"]) for r in sb.table("daily_holdings").select("value").eq("portfolio_id", TEST_PID).eq("date", last_date).execute().data)
    first_nav = sum(float(r["value"]) for r in sb.table("daily_holdings").select("value").eq("portfolio_id", TEST_PID).eq("date", NEW_INCEPTION).execute().data)
    print(f"  Daily_holdings dates: {len(dates)} ({dates[0]} -> {last_date})")
    print(f"  NAV at {NEW_INCEPTION}: ${first_nav:,.2f}  (should be ~$1,000,000)")
    print(f"  NAV at {last_date}:    ${last_nav:,.2f}")
    perf = (last_nav / first_nav - 1) * 100 if first_nav > 0 else 0
    print(f"  Implied perf inception->latest: {perf:+.2f}%")

    print(f"\nDone. Next:")
    print(f"  - Run `python daily_refresh.py` to update dividend_factors for new (ticker, {NEW_INCEPTION}) pairs")
    print(f"  - Reload Admin cockpit -> Portfolio_Test now has 4.5 months of chart history")


if __name__ == "__main__":
    main()
