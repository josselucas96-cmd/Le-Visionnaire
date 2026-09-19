"""One-shot recovery after the Sep 2026 pipeline outage (audit of 2026-09-19).

What happened
-------------
GitHub disabled both scheduled workflows on 2026-09-01 (60 days without a
commit). daily_holdings froze at 2026-08-30 (Bâtisseur/Nakamoto/test) and
2026-09-01 (Visionnaire). On top of that the audit found:
  * ALCPB.PA (Capital B) did a 1:10 reverse split on 2026-09-08 that was never
    applied to positions.shares — restarting the cron as-is would have written
    a +$770K phantom on the Nakamoto.
  * Visionnaire rows 2026-08-27, 08-28, 08-31, 09-01 hold the PREVIOUS day's
    closes (cron fired after midnight UTC, "latest close ≤ today" = yesterday).
  * Bâtisseur row 2026-06-03 was backfilled on 06-04 with the post-move book
    (AVGO/MA/NOW present, RACE absent) but pre-move cash → +3.5% phantom NAV.

What this script does (in order, idempotent, dry-run by default)
----------------------------------------------------------------
  0. Backup every row it will touch to backups/recovery_2026-09-19_<ts>.json
  1. Apply the ALCPB.PA 1:10 reverse split to positions (+ SPLIT transaction)
  2. Rewrite the 4 shifted Visionnaire rows via daily_refresh.refresh_portfolio
     (same code path as the cron, now with FX-as-of and guards)
  3. Repair Bâtisseur 2026-06-03: drop AVGO/MA/NOW rows, restore the RACE row
  4. Backfill every missing (portfolio, date) from 2026-08-31 to yesterday
  5. Refresh current_prices so the positions table shows live prices

Then run `python build_audit_workbook.py` (audit workbook rule).

Usage (from Streamlit_project/):
    python scripts/recover_2026_09_19.py            # dry-run: plan + numbers, no writes
    python scripts/recover_2026_09_19.py --execute  # apply
"""
import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import toml

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))
_s = toml.load(_PROJECT_ROOT / ".streamlit" / "secrets.toml")
os.environ["SUPABASE_URL"] = _s["supabase_url"]
os.environ["SUPABASE_KEY"] = _s["supabase_key"]

import yfinance as yf                      # noqa: E402
from supabase import create_client         # noqa: E402
import daily_refresh as dr                 # noqa: E402

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

SPLIT_TICKER, SPLIT_PID, SPLIT_RATIO, SPLIT_DATE = "ALCPB.PA", "nakamoto", 0.1, "2026-09-08"
VIS_SHIFTED_DATES = ["2026-08-27", "2026-08-28", "2026-08-31", "2026-09-01"]
BAT_BAD_DATE, BAT_DROP, BAT_RESTORE = "2026-06-03", ["AVGO", "MA", "NOW"], "RACE"
BACKFILL_FROM = "2026-08-31"
PIDS = ["visionnaire", "batisseur", "nakamoto", "test"]


def log(msg=""):
    print(msg, flush=True)


def close_on(ticker: str, d: str) -> float:
    price, actual = dr.fetch_close_price(ticker, d)
    if price is None or actual != d:
        raise RuntimeError(f"no close for {ticker} on {d} (got {actual})")
    return price


def nav_of(pid: str, d: str) -> tuple[float, int]:
    rows = sb.table("daily_holdings").select("ticker,value").eq("portfolio_id", pid).eq("date", d).execute().data
    return sum(float(r["value"]) for r in rows), sum(1 for r in rows if r["ticker"] != "CASH")


# ── 0. backup ────────────────────────────────────────────────────────────────
def backup() -> Path:
    out = {
        "positions_ALCPB": sb.table("positions").select("*").eq("portfolio_id", SPLIT_PID).eq("ticker", SPLIT_TICKER).execute().data,
        "visionnaire_shifted_rows": sb.table("daily_holdings").select("*").eq("portfolio_id", "visionnaire").in_("date", VIS_SHIFTED_DATES).execute().data,
        "batisseur_0603_rows": sb.table("daily_holdings").select("*").eq("portfolio_id", "batisseur").eq("date", BAT_BAD_DATE).execute().data,
        "current_prices": sb.table("current_prices").select("*").execute().data,
    }
    bdir = _PROJECT_ROOT / "backups"
    bdir.mkdir(exist_ok=True)
    p = bdir / f"recovery_2026-09-19_{datetime.now():%Y%m%d_%H%M%S}.json"
    p.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    return p


# ── 1. split ─────────────────────────────────────────────────────────────────
def step_split(execute: bool):
    log(f"\n[1] {SPLIT_TICKER} reverse split 1:{int(1/SPLIT_RATIO)} on {SPLIT_DATE}")
    p = sb.table("positions").select("*").eq("portfolio_id", SPLIT_PID).eq("ticker", SPLIT_TICKER).eq("is_active", True).execute().data
    if not p:
        log("    position not found -- skip"); return
    p = p[0]
    shares, pru = float(p["shares"]), float(p["entry_price"])
    already = sb.table("transactions").select("id").eq("portfolio_id", SPLIT_PID).eq("action", "SPLIT").eq("ticker_in", SPLIT_TICKER).eq("date", SPLIT_DATE).execute().data
    if already or shares < 50_000:
        log(f"    already applied (shares={shares:,.4f}, PRU={pru}) -- skip"); return
    new_shares, new_pru = round(shares * SPLIT_RATIO, 8), round(pru / SPLIT_RATIO, 6)
    new_units = round(float(p["units"]) * SPLIT_RATIO, 8) if p.get("units") is not None else None
    log(f"    shares {shares:,.4f} -> {new_shares:,.4f} | PRU {pru} -> {new_pru} | cost basis unchanged ${shares*pru:,.0f}")
    if not execute:
        return
    upd = {"shares": new_shares, "entry_price": new_pru}
    if new_units is not None:
        upd["units"] = new_units
    sb.table("positions").update(upd).eq("id", p["id"]).execute()
    sb.table("transactions").insert({
        "portfolio_id": SPLIT_PID, "date": SPLIT_DATE, "action": "SPLIT",
        "ticker_in": SPLIT_TICKER, "price_in": new_pru,
        "reason": f"{SPLIT_RATIO}-for-1 split (1:10 reverse split, {SPLIT_DATE}): shares x {SPLIT_RATIO}, PRU / {SPLIT_RATIO}. Applied 2026-09-19 (recovery).",
        "executed_at": datetime.now(timezone.utc).isoformat(),
    }).execute()
    log("    applied")


# ── 2. Visionnaire shifted rows ──────────────────────────────────────────────
def step_visionnaire(execute: bool):
    log(f"\n[2] Visionnaire: rewrite {', '.join(VIS_SHIFTED_DATES)} with the correct closes")
    for d in VIS_SHIFTED_DATES:
        before, _ = nav_of("visionnaire", d)
        if not execute:
            # show the NVDA close that WILL be written vs the one stored
            stored = sb.table("daily_holdings").select("price").eq("portfolio_id", "visionnaire").eq("date", d).eq("ticker", "NVDA").execute().data
            log(f"    {d}: NAV stored ${before:,.0f} | NVDA stored {float(stored[0]['price']):.2f} -> will write {dr.fetch_close_price('NVDA', d)[0]:.2f}")
            continue
        r = dr.refresh_portfolio(sb, "visionnaire", d)
        log(f"    {d}: NAV ${before:,.0f} -> ${r['nav']:,.0f}  ({r['rows_written']} rows)")


# ── 3. Bâtisseur 2026-06-03 ──────────────────────────────────────────────────
def step_batisseur(execute: bool):
    log(f"\n[3] Batisseur {BAT_BAD_DATE}: drop {BAT_DROP}, restore {BAT_RESTORE}")
    prev = sb.table("daily_holdings").select("shares").eq("portfolio_id", "batisseur").eq("date", "2026-06-02").eq("ticker", BAT_RESTORE).execute().data
    if not prev:
        log("    06-02 RACE row missing -- cannot restore, abort step"); return
    race_shares = float(prev[0]["shares"])
    race_close = close_on(BAT_RESTORE, BAT_BAD_DATE)   # NYSE, USD
    race_row = {"portfolio_id": "batisseur", "date": BAT_BAD_DATE, "ticker": BAT_RESTORE,
                "shares": round(race_shares, 8), "price": round(race_close, 4), "value": round(race_shares * race_close, 2)}
    nav_before, n_before = nav_of("batisseur", BAT_BAD_DATE)
    drop_val = sum(float(r["value"]) for r in sb.table("daily_holdings").select("value").eq("portfolio_id", "batisseur").eq("date", BAT_BAD_DATE).in_("ticker", BAT_DROP).execute().data)
    nav_after = nav_before - drop_val + race_row["value"]
    log(f"    NAV ${nav_before:,.0f} ({n_before} pos) -> ${nav_after:,.0f} ({n_before - len(BAT_DROP) + 1} pos) | RACE {race_shares:.4f} x {race_close:.2f} = ${race_row['value']:,.0f}")
    if not execute:
        return
    existing = {r["ticker"] for r in sb.table("daily_holdings").select("ticker").eq("portfolio_id", "batisseur").eq("date", BAT_BAD_DATE).execute().data}
    to_drop = [t for t in BAT_DROP if t in existing]
    if to_drop:
        sb.table("daily_holdings").delete().eq("portfolio_id", "batisseur").eq("date", BAT_BAD_DATE).in_("ticker", to_drop).execute()
    sb.table("daily_holdings").upsert([race_row], on_conflict="portfolio_id,date,ticker").execute()
    nav_chk, n_chk = nav_of("batisseur", BAT_BAD_DATE)
    log(f"    done: NAV ${nav_chk:,.0f} ({n_chk} pos)")


# ── 4. backfill ──────────────────────────────────────────────────────────────
def step_backfill(execute: bool):
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    start = datetime.strptime(BACKFILL_FROM, "%Y-%m-%d").date()
    days = [(start + timedelta(days=k)).isoformat() for k in range((date.today() - start).days)]
    log(f"\n[4] Backfill {BACKFILL_FROM} -> {yesterday} for {PIDS}")
    for pid in PIDS:
        present = {r["date"] for r in sb.table("daily_holdings").select("date").eq("portfolio_id", pid).gte("date", BACKFILL_FROM).lte("date", yesterday).execute().data}
        missing = [d for d in days if d not in present]
        if pid == "visionnaire":
            missing = [d for d in missing if d not in VIS_SHIFTED_DATES]
        log(f"    {pid}: {len(missing)} missing day(s)" + (f" [{missing[0]} .. {missing[-1]}]" if missing else ""))
        if not execute:
            continue
        for d in missing:
            try:
                r = dr.refresh_portfolio(sb, pid, d)
                extra = f"  propagated {len(r['propagated'])}" if r["propagated"] else ""
                skipped = f"  SKIPPED {r['skipped_tickers']}" if r["skipped_tickers"] else ""
                log(f"      {d}: NAV ${r['nav']:>12,.0f}  cash ${r['cash']:>10,.2f}{extra}{skipped}")
            except (dr.BookChangedAfterDate, dr.SuspiciousValueJump) as e:
                log(f"      {d}: REFUSED -- {e}"); break
            except Exception as e:
                log(f"      {d}: ERROR -- {e}"); break


# ── 5. current_prices ────────────────────────────────────────────────────────
def step_prices(execute: bool):
    log("\n[5] current_prices refresh (live)")
    if not execute:
        log("    would refresh all active tickers"); return
    r = dr.refresh_current_prices(sb, PIDS)
    log(f"    {r.get('ok')} tickers updated, failed: {r.get('failed')}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true", help="apply changes (default: dry-run)")
    args = ap.parse_args()
    mode = "EXECUTE" if args.execute else "DRY-RUN"
    log(f"=== recovery 2026-09-19 [{mode}] ===")
    if args.execute:
        log(f"[0] backup -> {backup()}")
    step_split(args.execute)
    step_visionnaire(args.execute)
    step_batisseur(args.execute)
    step_backfill(args.execute)
    step_prices(args.execute)
    log("\nSummary (last row per portfolio):")
    for pid in PIDS:
        last = sb.table("daily_holdings").select("date").eq("portfolio_id", pid).order("date", desc=True).limit(1).execute().data
        if last:
            nav, n = nav_of(pid, last[0]["date"])
            log(f"    {pid:<12} {last[0]['date']}  NAV ${nav:,.0f}  ({n} positions)  perf {nav/1e4-100:+.2f}%")
    if args.execute:
        log("\nNext: python build_audit_workbook.py")


if __name__ == "__main__":
    main()
