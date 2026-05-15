"""SURGICAL revert of the test TRIM on Bâtisseur BABA from 2026-05-15.

Strategy:
- Reads the exact TRIM transaction from DB (source of truth)
- Computes the inverse based on weight_out, entry_price_out, price_out
- Dry-run preview with full diff (before/after each value)
- User confirms with `y` before any write

What is DELETED:
- 1 row in `transactions` (the test TRIM)
- All rows in `position_snapshots` WHERE date='2026-05-15' AND snapshot_type='move'
- All rows in `daily_holdings` WHERE portfolio_id='batisseur' AND date='2026-05-15'
- File `snapshots/batisseur/2026-05-15.csv` if exists

What is RESTORED (UPDATE, not DELETE):
- `positions` BABA -> weight, units, shares restored (PRU intact)
- `portfolios` batisseur -> cash_units, cash_amount restored

What is PRESERVED untouched:
- All inception snapshots (Bâtisseur May 6 and others)
- All daily_holdings rows from May 5 to May 14
- All other portfolios (Visionnaire, Nakamoto) data
- All CSV snapshots in repo
"""
import sys
from pathlib import Path

import toml
from supabase import create_client


PORTFOLIO_ID = "batisseur"
TICKER = "BABA"
MOVE_DATE = "2026-05-15"
DEFAULT_INITIAL_CAPITAL = 1_000_000.0


def main():
    secrets = toml.load(Path(__file__).parent / ".streamlit" / "secrets.toml")
    sb = create_client(secrets["supabase_url"], secrets["supabase_key"])

    # ── 1. Find the TRIM transaction ──────────────────────────────────────────
    txns = (
        sb.table("transactions")
        .select("*")
        .eq("portfolio_id", PORTFOLIO_ID)
        .eq("ticker_out", TICKER)
        .eq("date", MOVE_DATE)
        .eq("action", "TRIM")
        .execute()
        .data
    )
    if not txns:
        print(f"ERROR: no TRIM found for {PORTFOLIO_ID} {TICKER} on {MOVE_DATE}. Nothing to revert.")
        sys.exit(0)
    if len(txns) > 1:
        print(f"ERROR: multiple TRIMs found ({len(txns)}). Bail out for safety.")
        for t in txns:
            print(f"  id={t['id']} weight_out={t['weight_out']} price_out={t['price_out']}")
        sys.exit(1)
    txn = txns[0]
    print(f"Found transaction id={txn['id']}, weight_out={txn['weight_out']}, "
          f"entry_price_out={txn['entry_price_out']}, price_out={txn['price_out']}")

    weight_out      = float(txn["weight_out"])
    entry_price_out = float(txn["entry_price_out"])  # PRU at trim time
    price_out       = float(txn["price_out"])         # exit price (real cash receipt)

    # ── 2. Read initial_capital for this portfolio ────────────────────────────
    cap_row = (
        sb.table("settings")
        .select("value")
        .eq("key", f"initial_capital_{PORTFOLIO_ID}")
        .execute()
        .data
    )
    initial_capital = float(cap_row[0]["value"]) if cap_row and cap_row[0].get("value") else DEFAULT_INITIAL_CAPITAL
    print(f"Initial capital: ${initial_capital:,.0f}")

    # ── 3. Compute restoration ────────────────────────────────────────────────
    shares_to_restore = (weight_out * initial_capital / 100.0) / entry_price_out
    cash_to_remove    = shares_to_restore * price_out

    print(f"\nReverse math:")
    print(f"  shares_to_restore = (weight_out x capital / 100) / PRU")
    print(f"                    = ({weight_out} x {initial_capital:,.0f} / 100) / {entry_price_out}")
    print(f"                    = {shares_to_restore:.8f} shares")
    print(f"  cash_to_remove    = shares x exit_price = {shares_to_restore:.6f} x {price_out}")
    print(f"                    = ${cash_to_remove:,.2f}")

    # ── 4. Read current position & portfolio state ────────────────────────────
    pos = (
        sb.table("positions")
        .select("*")
        .eq("portfolio_id", PORTFOLIO_ID)
        .eq("ticker", TICKER)
        .eq("is_active", True)
        .execute()
        .data
    )
    if not pos:
        print(f"ERROR: no active position for {TICKER}.")
        sys.exit(1)
    p = pos[0]
    cur_w = float(p["weight"])
    cur_units = float(p.get("units") or 0)
    cur_shares = float(p.get("shares") or 0)
    pru = float(p["entry_price"])

    pf = sb.table("portfolios").select("cash_units, cash_amount").eq("id", PORTFOLIO_ID).execute().data[0]
    cur_cash_units = float(pf.get("cash_units") or 0)
    cur_cash_amount = float(pf.get("cash_amount") or 0)

    # Target state (pre-trim, restored)
    new_w = round(cur_w + weight_out, 4)
    new_units = round(new_w / pru, 8) if pru > 0 else 0.0
    new_shares = round(cur_shares + shares_to_restore, 8)

    # Robust cash target: derive from all active positions post-revert (not by
    # subtracting from current, which may be corrupt/NULL). After restoring
    # BABA, sum of active weights gives the correct cash by identity:
    # cash_units = 100 - Σ weights ; cash_amount = cash_units × capital / 100
    all_active = (
        sb.table("positions")
        .select("ticker, weight")
        .eq("portfolio_id", PORTFOLIO_ID)
        .eq("is_active", True)
        .execute()
        .data
    )
    sum_w_post_revert = sum(
        (float(r["weight"] or 0) if r["ticker"] != TICKER else new_w)
        for r in all_active
    )
    new_cash_units  = round(100.0 - sum_w_post_revert, 6)
    new_cash_amount = round(new_cash_units * initial_capital / 100.0, 2)

    # ── 5. Read auxiliary rows to delete ──────────────────────────────────────
    snapshots_to_delete = (
        sb.table("position_snapshots")
        .select("portfolio_id, date, ticker, snapshot_type")
        .eq("portfolio_id", PORTFOLIO_ID)
        .eq("date", MOVE_DATE)
        .eq("snapshot_type", "move")
        .execute()
        .data
    )
    holdings_to_delete = (
        sb.table("daily_holdings")
        .select("portfolio_id, date, ticker")
        .eq("portfolio_id", PORTFOLIO_ID)
        .eq("date", MOVE_DATE)
        .execute()
        .data
    )
    csv_to_delete = Path(__file__).parent / "snapshots" / PORTFOLIO_ID / f"{MOVE_DATE}.csv"

    # ── 6. Dry-run preview ────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("DRY RUN -- would apply the following changes:")
    print("=" * 70)
    print(f"\n[positions] WHERE ticker='{TICKER}':")
    print(f"  weight       : {cur_w}        -> {new_w}")
    print(f"  units        : {cur_units:.8f} -> {new_units:.8f}")
    print(f"  shares       : {cur_shares:.8f} -> {new_shares:.8f}")
    print(f"  entry_price  : {pru}    (unchanged, PRU intact on TRIM)")
    print(f"\n[portfolios] WHERE id='{PORTFOLIO_ID}':")
    print(f"  cash_units   : {cur_cash_units} -> {new_cash_units}")
    print(f"  cash_amount  : ${cur_cash_amount:,.2f} -> ${new_cash_amount:,.2f}")
    print(f"\n[transactions] DELETE id={txn['id']}")
    print(f"[position_snapshots] DELETE {len(snapshots_to_delete)} rows (portfolio={PORTFOLIO_ID}, date={MOVE_DATE}, type=move)")
    print(f"[daily_holdings] DELETE {len(holdings_to_delete)} rows (portfolio={PORTFOLIO_ID}, date={MOVE_DATE})")
    print(f"[CSV file] DELETE {csv_to_delete} (exists: {csv_to_delete.exists()})")

    print("\nPRESERVED untouched:")
    print("  - Inception snapshot Bâtisseur (date='2026-05-06', type='initial')")
    print("  - daily_holdings rows May 5 -> May 14 for Bâtisseur")
    print("  - All Visionnaire and Nakamoto data")
    print("  - All other CSV files in snapshots/")

    # ── 7. Confirm and apply ──────────────────────────────────────────────────
    answer = input("\nApply this revert? [y/N]: ").strip().lower()
    if answer != "y":
        print("Aborted. Nothing written.")
        sys.exit(0)

    print("\nApplying...")
    # 1. Restore positions BABA
    sb.table("positions").update({
        "weight": new_w,
        "units":  new_units,
        "shares": new_shares,
    }).eq("id", p["id"]).execute()
    print(f"  [positions] {TICKER} restored")

    # 2. Restore portfolios cash
    sb.table("portfolios").update({
        "cash_units":  new_cash_units,
        "cash_amount": new_cash_amount,
    }).eq("id", PORTFOLIO_ID).execute()
    print(f"  [portfolios] {PORTFOLIO_ID} cash restored")

    # 3. Delete the TRIM transaction
    sb.table("transactions").delete().eq("id", txn["id"]).execute()
    print(f"  [transactions] id={txn['id']} deleted")

    # 4. Delete position_snapshots rows
    sb.table("position_snapshots").delete().eq("portfolio_id", PORTFOLIO_ID).eq(
        "date", MOVE_DATE
    ).eq("snapshot_type", "move").execute()
    print(f"  [position_snapshots] {len(snapshots_to_delete)} 'move' rows deleted")

    # 5. Delete daily_holdings rows (if any)
    if holdings_to_delete:
        sb.table("daily_holdings").delete().eq("portfolio_id", PORTFOLIO_ID).eq(
            "date", MOVE_DATE
        ).execute()
        print(f"  [daily_holdings] {len(holdings_to_delete)} rows deleted")

    # 6. Delete local CSV file (if exists)
    if csv_to_delete.exists():
        csv_to_delete.unlink()
        print(f"  [CSV] {csv_to_delete.name} deleted")

    print("\nDone. State restored to pre-test.")


if __name__ == "__main__":
    main()
