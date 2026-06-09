"""ONE-SHOT: apply the 3 BUYs that failed in the cockpit on 2026-06-04.

Cockpit successfully closed RACE (+11.7% perf, $349.91) but the 3 BUYs (AVGO, MA, NOW)
didn't reach the DB due to a silent failure in add_position whose error banner was
wiped by st.rerun(). This script writes them directly via supabase-py, bypassing the
cockpit's flow.

Intent (per Bâtisseur Rebalance #1 plan, executed 2026-06-04 15h35 Swiss):
  - AVGO @ $411.73, target 3% of NAV   → ~$29,537, ~71.74 shares
  - MA   @ $477.67, target 2% of NAV   → ~$19,692, ~41.23 shares
  - NOW  @ $121.41, target 2% of NAV   → ~$19,692, ~162.20 shares

USD estimates come straight from the cockpit confirmation modal so the result
exactly matches what would have been written.

USAGE:
    python apply_batisseur_buys.py            # DRY RUN
    python apply_batisseur_buys.py --confirm  # actually writes

Idempotency: refuses to run if AVGO / MA / NOW already active in batisseur.
"""
import argparse
import os
import sys
import toml
from pathlib import Path

# Resolve secrets.toml relative to this script so it works whether the script
# lives at the project root or in scripts/. Falls back to cwd for legacy.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SECRETS_PATH = _PROJECT_ROOT / ".streamlit" / "secrets.toml"
if not _SECRETS_PATH.exists():
    _SECRETS_PATH = Path(".streamlit/secrets.toml")
s = toml.load(_SECRETS_PATH)
os.environ["SUPABASE_URL"] = s.get("supabase_url")
os.environ["SUPABASE_KEY"] = s.get("supabase_key")
from supabase import create_client  # noqa: E402

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

PID = "batisseur"
EXECUTED_AT = "2026-06-04T13:35:00+00:00"  # 15h35 Swiss CEST = 13h35 UTC
ENTRY_DATE = "2026-06-04"
INITIAL_CAPITAL = 1_000_000.0  # _get_initial_capital fallback (no initial_capital_batisseur row)

# USD estimates from the cockpit confirmation modal — drives weight stored in DB.
# weight_db = usd_cost / initial_capital * 100  (matches add_position math when
# initial_capital == default fallback, which is the case here)
BUYS = [
    {
        "ticker": "AVGO", "name": "Broadcom Inc.",
        "price": 411.73, "usd_cost": 29537.0,
        "sector": "Tech", "geography": "USA", "thematic": "AI / Semi",
    },
    {
        "ticker": "MA", "name": "Mastercard Incorporated",
        "price": 477.67, "usd_cost": 19692.0,
        "sector": "Finance", "geography": "USA", "thematic": "Fintech / Payments",
    },
    {
        "ticker": "NOW", "name": "ServiceNow, Inc.",
        "price": 121.41, "usd_cost": 19692.0,
        "sector": "Tech", "geography": "USA", "thematic": "Software / SaaS",
    },
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--confirm", action="store_true", help="actually write to DB")
    args = ap.parse_args()

    # ── Idempotency: skip individually (don't abort the whole batch) ──
    existing = (
        sb.table("positions").select("ticker")
        .eq("portfolio_id", PID).eq("is_active", True)
        .in_("ticker", [b["ticker"] for b in BUYS])
        .execute().data
    )
    skip = {r["ticker"] for r in existing}
    if skip:
        print(f"SKIP (already active): {sorted(skip)}")
    buys_to_apply = [b for b in BUYS if b["ticker"] not in skip]
    if not buys_to_apply:
        print("Nothing to do.")
        sys.exit(0)

    # ── Compute rows ──
    pos_rows, tx_rows = [], []
    for b in buys_to_apply:
        new_db = round(b["usd_cost"] / INITIAL_CAPITAL * 100.0, 6)
        new_units = round(new_db / b["price"], 8)
        new_shares = round(b["usd_cost"] / b["price"], 8)

        pos_rows.append({
            "portfolio_id": PID,
            "ticker":       b["ticker"],
            "name":         b["name"],
            "isin":         None,
            "layer":        "Quality Compounders",
            "weight":       new_db,
            "entry_price":  b["price"],
            "entry_date":   ENTRY_DATE,
            "sector":       b["sector"],
            "geography":    b["geography"],
            "thematic":     b["thematic"],
            "thesis_short": "",
            "is_active":    True,
            "units":        new_units,
            "shares":       new_shares,
        })
        tx_rows.append({
            "portfolio_id": PID,
            "date":         ENTRY_DATE,
            "action":       "IN",
            "ticker_in":    b["ticker"],
            "price_in":     b["price"],
            "weight_in":    new_db,
            "reason":       "New position",
            "executed_at":  EXECUTED_AT,
        })

    print(f"\nMODE: {'WRITE' if args.confirm else 'DRY-RUN'}\n")
    print(f"{'ticker':6} {'weight':>9} {'shares':>12} {'units':>10} {'price':>10}  layer / sector / thematic")
    for p in pos_rows:
        print(f"{p['ticker']:6} {p['weight']:>9.4f} {p['shares']:>12.4f} {p['units']:>10.6f} {p['entry_price']:>10.2f}  "
              f"{p['layer']} / {p['sector']} / {p['thematic']}")
    print(f"\nexecuted_at = {EXECUTED_AT}")
    print(f"entry_date  = {ENTRY_DATE}")

    if not args.confirm:
        print("\nDRY RUN — nothing written. Re-run with --confirm to apply.")
        sys.exit(0)

    # ── WRITE ──
    for p in pos_rows:
        r = sb.table("positions").insert(p).execute()
        new_id = r.data[0]["id"] if r.data else "?"
        print(f"  + position    {p['ticker']:6}  id={new_id}")
    for t in tx_rows:
        sb.table("transactions").insert(t).execute()
        print(f"  + transaction IN {t['ticker_in']:6}  price={t['price_in']}")

    print(f"\nDONE. {len(pos_rows)} positions + {len(tx_rows)} transactions written.")


if __name__ == "__main__":
    main()
