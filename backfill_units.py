"""One-shot backfill for the units model migration (PR-1).

Computes, for each portfolio:
- positions.units = weight / entry_price  (active only; inactive get 0)
- portfolios.cash_units = 100 - sum(weight of active positions)

Math: NAV(0) = 100. Position at weight w%, PRU p → owns (w/p) notional units.
Value at any t = units × price(t). Same contribution as today's
`weight × (price/entry_price)` formula, but expressed as a stable quantity
that future moves will not retroactively rewrite.

Run once after the SQL migration that adds the two columns. Idempotent.

Usage:
    cd Streamlit_project
    python backfill_units.py
"""
import sys
from pathlib import Path

import toml
from supabase import create_client


def load_secrets():
    secrets_path = Path(__file__).parent / ".streamlit" / "secrets.toml"
    if not secrets_path.exists():
        sys.exit(f"Missing {secrets_path} — cannot connect to Supabase.")
    return toml.load(secrets_path)


def main():
    secrets = load_secrets()
    sb = create_client(secrets["supabase_url"], secrets["supabase_key"])

    portfolios = sb.table("portfolios").select("id, name").order("display_order").execute().data
    print(f"\nFound {len(portfolios)} portfolios.\n")

    plan = []  # list of (kind, label, payload, target_id)
    for pf in portfolios:
        portfolio_id = pf["id"]
        positions = (
            sb.table("positions")
            .select("id, ticker, weight, entry_price, is_active")
            .eq("portfolio_id", portfolio_id)
            .order("ticker")
            .execute()
            .data
        )

        print(f"── {pf['name']} ({portfolio_id}) — {len(positions)} positions")
        sum_active_weight = 0.0
        for p in positions:
            if p.get("is_active") and p.get("weight") and p.get("entry_price"):
                units = float(p["weight"]) / float(p["entry_price"])
                units = round(units, 8)
                plan.append(("position", f"  {p['ticker']:8s} w={p['weight']:>7} entry={p['entry_price']:>9} → units={units:.8f}",
                             {"units": units}, p["id"]))
                sum_active_weight += float(p["weight"])
            else:
                plan.append(("position_inactive", f"  {p['ticker']:8s} inactive → units=0",
                             {"units": 0}, p["id"]))

        cash_units = round(100.0 - sum_active_weight, 4)
        plan.append(("portfolio", f"  → cash_units = {cash_units} (invested = {sum_active_weight:.2f}%)",
                     {"cash_units": cash_units}, portfolio_id))
        print()

    # Preview
    print("=" * 70)
    print("PLAN (DRY RUN — nothing written yet):")
    print("=" * 70)
    for kind, label, _, _ in plan:
        print(label)

    print()
    answer = input("Apply these changes to Supabase? [y/N]: ").strip().lower()
    if answer != "y":
        print("Aborted. No changes written.")
        return

    # Apply
    print("\nWriting to Supabase...")
    for kind, label, payload, target_id in plan:
        if kind == "portfolio":
            sb.table("portfolios").update(payload).eq("id", target_id).execute()
        else:
            sb.table("positions").update(payload).eq("id", target_id).execute()
    print(f"Done. {len(plan)} rows updated.")


if __name__ == "__main__":
    main()
