"""One-shot: backfill the missing 2026-05-15 (Friday) close row in
daily_holdings for the 3 portfolios.

WHY this is needed
------------------
`lazy_write_holdings` only writes "today's" row when a visitor loads the
page AND yfinance has today's close. Nobody visited the site between
Friday 22h CH (US market close) and Saturday morning. Now we're Saturday
13h CH, lazy_write tries to write "today" (Saturday, no market data) and
returns 0. Friday's close is permanently missing unless we backfill.

WHAT this writes
----------------
For each portfolio (visionnaire, batisseur, nakamoto):
- For each active ticker T: row (portfolio, date=2026-05-15, ticker=T,
  shares=current_shares, price=yfinance_close_2026-05-15, value=shares×price)
- CASH row: shares=last_known_cash$, price=1.0, value=last_known_cash$

ASSUMPTION
----------
No moves happened between 2026-05-14 close and 2026-05-15 close.
- Visionnaire: 0 transactions on 2026-05-15 (verified)
- Bâtisseur:   0 transactions (BABA test trim was REVERTED same day)
- Nakamoto:    0 transactions

→ shares per ticker on 15/05 close = shares per ticker on 14/05 close
→ cash on 15/05 close = cash on 14/05 close (CASH row in daily_holdings)

PRESERVES
---------
- All existing daily_holdings rows for dates < 2026-05-15 (immutable past)
- All other tables (positions, transactions, snapshots)

IDEMPOTENT
----------
Uses upsert on (portfolio_id, date, ticker). Safe to re-run.

Dry-run preview first; user types `y` to apply.
"""
import sys
from pathlib import Path

import toml
import yfinance as yf
from supabase import create_client


TARGET_DATE = "2026-05-15"
PORTFOLIOS = ["visionnaire", "batisseur", "nakamoto"]


def fetch_close_price(ticker: str) -> float | None:
    """Fetch yfinance Close for TARGET_DATE."""
    try:
        df = yf.download(ticker, start="2026-05-15", end="2026-05-17",
                         progress=False, auto_adjust=False)
        if df.empty or "Close" not in df.columns:
            return None
        # Get the row for TARGET_DATE
        from pandas import Timestamp
        target_ts = Timestamp(TARGET_DATE)
        if target_ts in df.index:
            return float(df.loc[target_ts, "Close"].iloc[0]) if hasattr(df.loc[target_ts, "Close"], 'iloc') else float(df.loc[target_ts, "Close"])
        return None
    except Exception as e:
        print(f"  ! {ticker}: yfinance error ({e})")
        return None


def main():
    secrets = toml.load(Path(__file__).parent / ".streamlit" / "secrets.toml")
    sb = create_client(secrets["supabase_url"], secrets["supabase_key"])

    # Safety: verify no transactions on TARGET_DATE for any portfolio
    print(f"Safety check: confirming 0 transactions on {TARGET_DATE}...")
    total_txns = 0
    for pid in PORTFOLIOS:
        n = len(sb.table("transactions").select("id").eq("portfolio_id", pid).eq("date", TARGET_DATE).execute().data)
        print(f"  {pid:13} transactions on {TARGET_DATE}: {n}")
        total_txns += n
    if total_txns > 0:
        print(f"\nABORTING: {total_txns} transaction(s) found on {TARGET_DATE}.")
        print("The 'no moves between 14/05 close and 15/05 close' assumption is violated.")
        print("A more sophisticated backfill is needed (per-transaction replay).")
        sys.exit(1)

    # Verify no existing daily_holdings row for TARGET_DATE (so we won't accidentally overwrite)
    print(f"\nSafety check: confirming 0 daily_holdings rows on {TARGET_DATE}...")
    total_rows = 0
    for pid in PORTFOLIOS:
        n = len(sb.table("daily_holdings").select("ticker").eq("portfolio_id", pid).eq("date", TARGET_DATE).execute().data)
        print(f"  {pid:13} daily_holdings on {TARGET_DATE}: {n}")
        total_rows += n
    if total_rows > 0:
        print(f"\nNote: {total_rows} existing rows for {TARGET_DATE}. Upsert will overwrite them.")
        answer = input("Continue? [y/N]: ").strip().lower()
        if answer != "y":
            print("Aborted.")
            sys.exit(0)

    # Per portfolio, build the rows
    print(f"\n{'='*70}\nBuilding backfill plan for {TARGET_DATE}\n{'='*70}")
    all_rows = []
    summaries = []
    for pid in PORTFOLIOS:
        print(f"\n[{pid}]")
        # Get active positions (= 14/05 close state = 15/05 close state, no moves)
        positions = sb.table("positions").select("ticker, shares").eq("portfolio_id", pid).eq("is_active", True).execute().data
        # Get CASH row from 14/05 (yesterday)
        cash_row = sb.table("daily_holdings").select("value").eq("portfolio_id", pid).eq("ticker", "CASH").eq("date", "2026-05-14").execute().data
        if not cash_row:
            print(f"  ERROR: no CASH row for 2026-05-14, aborting.")
            sys.exit(1)
        cash_value = float(cash_row[0]["value"])

        nav = cash_value
        rows = [{
            "portfolio_id": pid,
            "date":         TARGET_DATE,
            "ticker":       "CASH",
            "shares":       round(cash_value, 2),
            "price":        1.0,
            "value":        round(cash_value, 2),
        }]
        for p in positions:
            tk = p["ticker"]
            shares = float(p.get("shares") or 0)
            if shares <= 0:
                continue
            price = fetch_close_price(tk)
            if price is None:
                print(f"  WARN {tk}: no Friday close, skipping (will leave gap)")
                continue
            value = shares * price
            nav += value
            rows.append({
                "portfolio_id": pid,
                "date":         TARGET_DATE,
                "ticker":       tk,
                "shares":       round(shares, 8),
                "price":        round(price, 4),
                "value":        round(value, 2),
            })
        print(f"  Built {len(rows)} rows (incl. CASH), NAV @ {TARGET_DATE} close = ${nav:,.2f}")
        all_rows.extend(rows)
        summaries.append((pid, len(rows), nav))

    print(f"\n{'='*70}\nDRY RUN summary\n{'='*70}")
    for pid, n, nav in summaries:
        print(f"  {pid:13} {n:3} rows  NAV close 15/05 = ${nav:,.2f}")
    print(f"  TOTAL: {len(all_rows)} rows across {len(PORTFOLIOS)} portfolios")

    answer = input("\nApply UPSERT to daily_holdings? [y/N]: ").strip().lower()
    if answer != "y":
        print("Aborted. Nothing written.")
        sys.exit(0)

    print("\nApplying...")
    # Upsert in batches per portfolio
    for pid in PORTFOLIOS:
        pid_rows = [r for r in all_rows if r["portfolio_id"] == pid]
        if not pid_rows:
            continue
        sb.table("daily_holdings").upsert(pid_rows, on_conflict="portfolio_id,date,ticker").execute()
        print(f"  {pid:13} {len(pid_rows)} rows upserted")

    # Verify
    print("\nVerification (re-read):")
    for pid in PORTFOLIOS:
        rows = sb.table("daily_holdings").select("ticker, value").eq("portfolio_id", pid).eq("date", TARGET_DATE).execute().data
        nav = sum(float(r["value"] or 0) for r in rows)
        print(f"  {pid:13} {len(rows):3} rows for {TARGET_DATE}, NAV = ${nav:,.2f}")

    print("\nDone. Reload public pages to see the 15/05 point on charts.")


if __name__ == "__main__":
    main()
