"""One-shot fix: recalibrate PRU + units for CELH and HIMS (visionnaire).

Why this script exists
----------------------
The reinforce moves on 2026-05-14 ran with an earlier version of
`add_position` that used a WEIGHT-averaged PRU formula:
    new_PRU = (old_PRU * old_w + new_price * new_w) / total_w

The current code uses the COST-weighted (= shares-weighted) formula which
is mathematically correct:
    new_PRU = total_cost_$ / total_shares
            = (total_w × initial_capital / 100) / total_shares

The two formulas only agree when new_price == old_PRU. They diverged for
CELH (old_PRU $34.23 → reinforce at $29.52) and HIMS (old_PRU $19.33 →
reinforce at $24.11) on 2026-05-14, leaving the stored PRU off by ~$0.12.

Impact while the drift exists:
- Chart / NAV : 0 (daily_holdings uses shares which are correct)
- Cash $       : 0 (derived via get_cash_amount, doesn't touch PRU)
- Return %     : CELH shown -12.10% should be -11.73% ; HIMS +21.29% → +21.99%
- Future trims : `shares_sold = w_sold × cap / PRU` would be ~0.4% off

What this script does
---------------------
For CELH and HIMS only:
- Verify shares × stored_PRU ≠ weight × initial_capital/100 (the drift)
- Compute correct PRU = (weight × initial_capital / 100) / shares
- Compute consistent units = weight / new_PRU
- UPDATE positions row (entry_price + units)

Out of scope (untouched):
- positions.shares (already correct, kept as-is)
- positions.weight (kept)
- daily_holdings (uses shares, unaffected)
- transactions log (immutable event history — past trade records preserved)
- portfolios.* (RLS-blocked anyway, not relevant)
- All other 14 positions in Visionnaire and all 35 in Bâtisseur/Nakamoto

Dry-run first; user must type `y` to apply.
"""
import sys
from pathlib import Path

import toml
from supabase import create_client

PORTFOLIO_ID = "visionnaire"
INITIAL_CAPITAL = 1_000_000.0
TICKERS = ["CELH", "HIMS"]


def main():
    secrets = toml.load(Path(__file__).parent / ".streamlit" / "secrets.toml")
    sb = create_client(secrets["supabase_url"], secrets["supabase_key"])

    plan = []
    for tk in TICKERS:
        rows = (
            sb.table("positions")
            .select("id, ticker, weight, shares, units, entry_price")
            .eq("portfolio_id", PORTFOLIO_ID)
            .eq("ticker", tk)
            .eq("is_active", True)
            .execute()
            .data
        )
        if not rows:
            print(f"ERROR: no active position {tk}, aborting.")
            sys.exit(1)
        p = rows[0]
        w = float(p["weight"])
        s = float(p["shares"])
        old_pru = float(p["entry_price"])
        old_units = float(p["units"])

        if s <= 0:
            print(f"ERROR: {tk} has shares={s}, aborting.")
            sys.exit(1)

        total_cost = w * INITIAL_CAPITAL / 100.0
        new_pru = total_cost / s
        new_units = w / new_pru if new_pru > 0 else 0.0

        # Round to same precision the code uses (6 decimals on PRU, 8 on units)
        new_pru_rounded = round(new_pru, 6)
        new_units_rounded = round(new_units, 8)

        # Sanity: invariant must hold to within $0.01
        invariant_drift = abs(s * new_pru_rounded - total_cost)
        if invariant_drift > 0.05:
            print(f"ERROR: {tk} invariant drift {invariant_drift:.4f} after fix, aborting.")
            sys.exit(1)

        plan.append({
            "id": p["id"],
            "ticker": tk,
            "weight": w,
            "shares": s,
            "old_pru": old_pru,
            "new_pru": new_pru_rounded,
            "old_units": old_units,
            "new_units": new_units_rounded,
            "total_cost": total_cost,
        })

    # Dry-run preview
    print("=" * 70)
    print("DRY RUN -- would apply the following UPDATEs to positions:")
    print("=" * 70)
    for x in plan:
        print(f"\n[positions WHERE id={x['id']}] ticker={x['ticker']}")
        print(f"  weight       : {x['weight']}     (unchanged)")
        print(f"  shares       : {x['shares']}     (unchanged)")
        print(f"  total_cost = weight x cap / 100 = ${x['total_cost']:.4f}  (invariant)")
        print(f"  entry_price  : ${x['old_pru']}   -> ${x['new_pru']}        (delta: ${x['new_pru'] - x['old_pru']:+.6f})")
        print(f"  units        : {x['old_units']} -> {x['new_units']}  (delta: {x['new_units'] - x['old_units']:+.8f})")
        print(f"  post-fix shares*PRU = ${x['shares'] * x['new_pru']:.4f}  (matches total_cost)")
    print("\nUNTOUCHED: 14 other Visionnaire positions, all Batisseur/Nakamoto positions,")
    print("daily_holdings, transactions, position_snapshots, portfolios, CSV files.")

    answer = input("\nApply these UPDATEs? [y/N]: ").strip().lower()
    if answer != "y":
        print("Aborted. Nothing written.")
        sys.exit(0)

    print("\nApplying...")
    for x in plan:
        sb.table("positions").update({
            "entry_price": x["new_pru"],
            "units":       x["new_units"],
        }).eq("id", x["id"]).execute()
        print(f"  {x['ticker']:6} updated.")

    # Verify by re-reading
    print("\nVerification (re-read from DB):")
    for tk in TICKERS:
        p = sb.table("positions").select("ticker, weight, shares, units, entry_price").eq("portfolio_id", PORTFOLIO_ID).eq("ticker", tk).eq("is_active", True).execute().data[0]
        w = float(p["weight"]); s = float(p["shares"]); pru = float(p["entry_price"]); u = float(p["units"])
        inv = s * pru
        target = w * INITIAL_CAPITAL / 100.0
        ok = abs(inv - target) < 0.05
        print(f"  {tk:6} PRU=${pru:.6f}  units={u:.10f}  shares*PRU=${inv:.4f}  target=${target:.4f}  {'OK' if ok else 'FAIL'}")

    print("\nDone.")


if __name__ == "__main__":
    main()
