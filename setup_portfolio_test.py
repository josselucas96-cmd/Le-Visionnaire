"""One-shot: create the Admin-only Portfolio_Test sandbox.

What this script does:
1. INSERT portfolio row `test` (is_active=False so it's hidden from the
   landing page, color #22C55E green to differentiate from the 3 live ones).
2. INSERT setting `initial_capital_test = 1000000`.
3. Fetch yfinance Close on 2026-05-15 (T-1) for all 26 active tickers in
   Bâtisseur — recomputed PRU for a clean $1M start.
4. Copy Bâtisseur positions with entry_date=2026-05-16, entry_price = close
   15/05, shares = (weight × $1M / 100) / entry_price, units = weight / entry_price.
5. INSERT T-1 anchor row in daily_holdings (test, 2026-05-15, CASH, $1M).
6. Generate snapshots/test/2026-05-16.csv (CSV mirror for recovery).

Safety:
- Aborts if portfolio 'test' already exists (no overwrite — user must DROP first).
- Dry-run preview before any write. User confirms with `y`.
- Idempotent on subsequent runs (refuses to overwrite).

After running:
- Pull the latest code (Admin.py modified to show Test in the selector).
- Open the Admin cockpit → 4th card "Portfolio_Test" → click → start testing.
- Next cron run (or manual `python daily_refresh.py --date 2026-05-16`)
  will write the day-0 daily_holdings rows for Test.
"""
import csv
import sys
from datetime import date as _date, datetime, timezone
from pathlib import Path

import toml
import yfinance as yf
import pandas as pd
from supabase import create_client


TEST_PID         = "test"
TEST_NAME        = "Portfolio_Test"
TEST_DESC        = "Sandbox portfolio for infrastructure testing. Admin-only, copy of Bâtisseur with green color."
TEST_COLOR       = "#22C55E"  # vibrant green
INITIAL_CAPITAL  = 1_000_000.0
INCEPTION_DATE   = "2026-05-16"
T_MINUS_1        = "2026-05-15"
SOURCE_PID       = "batisseur"  # we copy this portfolio's composition
BENCH_PRIMARY    = "SPY"
BENCH_PRIMARY_LBL = "S&P 500"
BENCH_SECONDARY  = "QQQ"
BENCH_SECONDARY_LBL = "Nasdaq 100"


def fetch_close_15_05(ticker: str) -> float | None:
    """Yfinance Close on 2026-05-15 for `ticker` (or latest ≤ that date)."""
    try:
        df = yf.download(ticker, start="2026-05-13", end="2026-05-17",
                         progress=False, auto_adjust=False)
        if df.empty or "Close" not in df.columns:
            return None
        df = df[df.index <= pd.Timestamp(T_MINUS_1)]
        if df.empty:
            return None
        close = df["Close"].iloc[-1]
        return float(close.iloc[0]) if hasattr(close, "iloc") else float(close)
    except Exception as e:
        print(f"  ! {ticker}: yfinance error ({e})")
        return None


def main():
    secrets = toml.load(Path(__file__).parent / ".streamlit" / "secrets.toml")
    sb = create_client(secrets["supabase_url"], secrets["supabase_key"])

    # PRE-REQ: portfolio 'test' row + setting must already exist (created via
    # SQL in Supabase UI because anon key can't INSERT into portfolios — RLS).
    existing = sb.table("portfolios").select("id").eq("id", TEST_PID).execute().data
    if not existing:
        print(f"ABORT: portfolio '{TEST_PID}' not found in DB.")
        print(f"\nRun this SQL in Supabase SQL Editor first:\n")
        print(f"""INSERT INTO public.portfolios (
    id, name, description, inception_date, initial_capital,
    benchmark_primary, benchmark_primary_label,
    benchmark_secondary, benchmark_secondary_label,
    color_primary, is_active, display_order
) VALUES (
    '{TEST_PID}',
    '{TEST_NAME}',
    '{TEST_DESC}',
    '{INCEPTION_DATE}',
    {int(INITIAL_CAPITAL)},
    '{BENCH_PRIMARY}', '{BENCH_PRIMARY_LBL}',
    '{BENCH_SECONDARY}', '{BENCH_SECONDARY_LBL}',
    '{TEST_COLOR}',
    false,
    99
);

INSERT INTO public.settings (key, value)
VALUES ('initial_capital_{TEST_PID}', '{int(INITIAL_CAPITAL)}')
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
""")
        print(f"Then re-run this script.")
        sys.exit(1)

    # Re-run guard: if positions already exist for test, refuse to duplicate
    existing_positions = sb.table("positions").select("id").eq("portfolio_id", TEST_PID).execute().data
    if existing_positions:
        print(f"ABORT: portfolio '{TEST_PID}' already has {len(existing_positions)} positions. Refusing to duplicate.")
        print(f"To reset: DELETE FROM positions WHERE portfolio_id = '{TEST_PID}';")
        print(f"          DELETE FROM daily_holdings WHERE portfolio_id = '{TEST_PID}';")
        sys.exit(1)

    # SAFETY CHECK: source portfolio must exist
    source_pf = sb.table("portfolios").select("*").eq("id", SOURCE_PID).execute().data
    if not source_pf:
        print(f"ABORT: source portfolio '{SOURCE_PID}' not found.")
        sys.exit(1)

    # FETCH source positions
    source_positions = (
        sb.table("positions").select("*")
        .eq("portfolio_id", SOURCE_PID).eq("is_active", True)
        .execute().data
    )
    if not source_positions:
        print(f"ABORT: source portfolio '{SOURCE_PID}' has no active positions.")
        sys.exit(1)

    print(f"Fetching close 2026-05-15 for {len(source_positions)} tickers from yfinance...")
    new_positions = []
    failed = []
    for sp in source_positions:
        tk = sp["ticker"]
        weight = float(sp["weight"])
        close = fetch_close_15_05(tk)
        if close is None or close <= 0:
            failed.append(tk)
            continue
        cost = weight * INITIAL_CAPITAL / 100.0
        new_shares = round(cost / close, 8)
        new_units = round(weight / close, 8)
        new_positions.append({
            "portfolio_id":             TEST_PID,
            "ticker":                   tk,
            "name":                     sp.get("name"),
            "isin":                     sp.get("isin"),
            "layer":                    sp.get("layer"),
            "weight":                   weight,
            "units":                    new_units,
            "shares":                   new_shares,
            "entry_price":              round(close, 4),
            "entry_date":               INCEPTION_DATE,
            "is_active":                True,
            "sector":                   sp.get("sector"),
            "geography":                sp.get("geography"),
            "thematic":                 sp.get("thematic"),
            "thesis_short":             sp.get("thesis_short"),
            "expected_revenue_growth":  sp.get("expected_revenue_growth"),
            "expected_gross_margin":    sp.get("expected_gross_margin"),
            "expected_op_margin":       sp.get("expected_op_margin"),
            "expected_fcf_margin":      sp.get("expected_fcf_margin"),
        })

    if failed:
        print(f"WARNING: {len(failed)} tickers failed yfinance fetch: {failed}")
        print(f"They will be SKIPPED from the test portfolio.")

    total_weight = sum(float(p["weight"]) for p in new_positions)
    cash_pct = 100.0 - total_weight
    cash_dollars = round(INITIAL_CAPITAL * cash_pct / 100.0, 2)

    # DRY-RUN PREVIEW
    print()
    print("=" * 70)
    print(f"DRY RUN -- portfolio row + setting already exist (created via SQL).")
    print("Would write the following to complete the setup:")
    print("=" * 70)
    print(f"\n[positions] : {len(new_positions)} rows (copy of {SOURCE_PID} with entry_price = close 2026-05-15)")
    print(f"  total weight: {total_weight:.2f}%  -> cash: {cash_pct:.2f}% = ${cash_dollars:,.2f}")
    print(f"\n[daily_holdings] T-1 anchor: ({TEST_PID}, {T_MINUS_1}, CASH, {INITIAL_CAPITAL}, 1.0, {INITIAL_CAPITAL})")
    print(f"\n[CSV] snapshots/{TEST_PID}/{INCEPTION_DATE}.csv (recovery mirror)")
    print()

    answer = input("Apply? [y/N]: ").strip().lower()
    if answer != "y":
        print("Aborted.")
        sys.exit(0)

    # APPLY
    print("\nApplying...")

    # Step 1: positions
    sb.table("positions").insert(new_positions).execute()
    print(f"  [positions]  {len(new_positions)} rows inserted")

    # Step 1b: IN transactions — required so the cron's derive_cash_at_date
    # sees the cost basis subtraction and computes cash = $55K (not $1M).
    # Without these, daily_refresh would write NAV = positions + $1M = wrong.
    now_iso = datetime.now(timezone.utc).isoformat()
    txns = [{
        "portfolio_id": TEST_PID,
        "date":         INCEPTION_DATE,
        "action":       "IN",
        "ticker_in":    p["ticker"],
        "price_in":     p["entry_price"],
        "weight_in":    p["weight"],
        "reason":       f"New position ({TEST_NAME} inception)",
        "executed_at":  now_iso,
    } for p in new_positions]
    sb.table("transactions").insert(txns).execute()
    print(f"  [transactions] {len(txns)} IN rows inserted (so cron derives cash correctly)")

    # Step 2: T-1 anchor
    sb.table("daily_holdings").upsert([{
        "portfolio_id": TEST_PID,
        "date":         T_MINUS_1,
        "ticker":       "CASH",
        "shares":       INITIAL_CAPITAL,
        "price":        1.0,
        "value":        INITIAL_CAPITAL,
    }], on_conflict="portfolio_id,date,ticker").execute()
    print(f"  [daily_holdings] T-1 anchor inserted ({T_MINUS_1} CASH = ${INITIAL_CAPITAL:,.0f})")

    # Step 3: CSV snapshot
    snap_dir = Path(__file__).parent / "snapshots" / TEST_PID
    snap_dir.mkdir(parents=True, exist_ok=True)
    snap_path = snap_dir / f"{INCEPTION_DATE}.csv"
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
    print(f"  [CSV]        {snap_path}")

    print(f"\nDone. Portfolio_Test created with {len(new_positions)} positions, total weight {total_weight:.2f}%, cash {cash_pct:.2f}%.")
    print(f"\nNext: pull latest code (Admin.py modified) + open the cockpit. Then run:")
    print(f"  python daily_refresh.py --date {INCEPTION_DATE}")
    print(f"to populate the day-0 daily_holdings rows for {TEST_PID}.")


if __name__ == "__main__":
    main()
