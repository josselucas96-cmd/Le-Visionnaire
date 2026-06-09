"""ONE-SHOT migration: convert existing foreign-currency positions to the USD
model (true share counts + USD entry prices) and restate their daily_holdings
history with historical FX.

Why
---
Before the FX fix, foreign positions stored shares = dollar_cost / native_price
(the listing price was taken as USD). The intended USD exposure was correct at
entry, but: (a) the share count is wrong, (b) the position ignored currency
moves since entry. Now that the code values everything in USD, we must fix the
existing data so it stays consistent (else turning on FX would crash these
positions by the FX factor).

Per foreign position:
    fx_entry        = FX(currency, entry_date)
    shares_true     = shares_old / fx_entry            # real # of shares
    entry_price_usd = entry_price_old * fx_entry       # entry price in USD
  (check: shares_true * entry_price_usd == shares_old * entry_price_old = cost)

Per daily_holdings row of a foreign ticker (uses FX of THAT date):
    price_usd = price_native * FX(currency, date)
    shares    = shares_old / fx_entry
    value     = value_old * FX(currency, date) / fx_entry

USAGE
-----
    python migrate_fx_usd.py            # DRY RUN — prints planned changes
    python migrate_fx_usd.py --confirm  # actually writes

Idempotency guard: writes a `fx_usd_migration` flag in `settings`; refuses to
run again once set (prevents accidental double-conversion).
"""
import argparse
import sys
import toml
import os
from pathlib import Path
import pandas as pd
import yfinance as yf

# Resolve secrets.toml relative to this script so it works whether the script
# lives at the project root or in scripts/. Falls back to cwd for legacy.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SECRETS_PATH = _PROJECT_ROOT / ".streamlit" / "secrets.toml"
if not _SECRETS_PATH.exists():
    _SECRETS_PATH = Path(".streamlit/secrets.toml")  # legacy: script run from project root
s = toml.load(_SECRETS_PATH)
os.environ["SUPABASE_URL"] = s.get("supabase_url")
os.environ["SUPABASE_KEY"] = s.get("supabase_key")
from supabase import create_client  # noqa: E402

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

_MINOR_UNIT = {"GBp": "GBP", "GBX": "GBP", "ZAc": "ZAR", "ZAX": "ZAR", "ILA": "ILS"}
MIGRATION_KEY = "fx_usd_migration"


def fx_series(currency: str, start: str) -> pd.Series:
    """Daily FX (native->USD) series, forward-filled. Handles pence (/100).
    Retries on transient yfinance failures; raises if the series is empty."""
    import time
    major = _MINOR_UNIT.get(currency, currency)
    last_err = None
    for attempt in range(1, 5):
        try:
            df = yf.download(f"{major}USD=X", start=start, progress=False, auto_adjust=False)
            sclose = df["Close"]
            if hasattr(sclose, "columns"):
                sclose = sclose.iloc[:, 0]
            sclose.index = pd.to_datetime(sclose.index.date)
            sclose = sclose.dropna()
            if len(sclose) > 0:
                return sclose / 100.0 if currency in _MINOR_UNIT else sclose
        except Exception as e:
            last_err = e
        time.sleep(2 * attempt)
    raise RuntimeError(f"FX download failed for {currency} ({major}USD=X) after retries: {last_err}")


def fx_on(series: pd.Series, d: str) -> float:
    d = pd.Timestamp(d)
    s2 = series[series.index <= d]
    if len(s2) == 0:
        return float(series.iloc[0])  # date before series start -> earliest rate
    return float(s2.iloc[-1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--confirm", action="store_true", help="actually write to DB")
    args = ap.parse_args()

    # ── idempotency guard ──
    flag = sb.table("settings").select("value").eq("key", MIGRATION_KEY).execute().data
    if flag and str(flag[0].get("value")).lower() in ("true", "1", "done"):
        print("ALREADY MIGRATED (settings.fx_usd_migration set). Aborting.")
        sys.exit(0)

    # ── foreign positions ──
    cps = {r["ticker"]: (r.get("currency") or "USD")
           for r in sb.table("current_prices").select("ticker, currency").execute().data}
    positions = sb.table("positions").select(
        "id, portfolio_id, ticker, entry_date, weight, entry_price, shares, units, is_active"
    ).eq("is_active", True).execute().data
    foreign = [p for p in positions if cps.get(p["ticker"], "USD") not in ("USD", None)]

    if not foreign:
        print("No foreign positions found. Nothing to do.")
        sys.exit(0)

    min_entry = min(p["entry_date"] for p in foreign)
    series_cache: dict[str, pd.Series] = {}

    def series_for(ccy):
        if ccy not in series_cache:
            series_cache[ccy] = fx_series(ccy, str(min_entry))
        return series_cache[ccy]

    print(f"{'MODE':6} {'DRY-RUN' if not args.confirm else 'WRITE'}\n")
    print(f"{'ticker':10}{'ccy':5}{'fx_entry':>9}  {'shares':>14} -> {'shares_true':>14}   {'entry$':>9} -> {'entry_usd':>9}")
    pos_updates = []
    for p in foreign:
        ccy = cps[p["ticker"]]
        fe = fx_on(series_for(ccy), p["entry_date"])
        sh_old = float(p["shares"]); ep_old = float(p["entry_price"]); w = float(p["weight"])
        sh_new = sh_old / fe
        ep_new = ep_old * fe
        un_new = round(w / ep_new, 8) if ep_new > 0 else 0.0
        pos_updates.append((p["id"], p["ticker"], ccy, fe, sh_new, ep_new, un_new))
        print(f"{p['ticker']:10}{ccy:5}{fe:9.4f}  {sh_old:14.4f} -> {sh_new:14.4f}   {ep_old:9.2f} -> {ep_new:9.2f}")

    # ── daily_holdings restatement ──
    print("\n-- daily_holdings restatement (foreign tickers) --")
    dh_updates = []
    fx_entry_by_id = {u[0]: u[3] for u in pos_updates}
    for p in foreign:
        ccy = cps[p["ticker"]]
        ser = series_for(ccy)
        fe = next(u[3] for u in pos_updates if u[0] == p["id"])
        rows = sb.table("daily_holdings").select("date, shares, price, value").eq(
            "portfolio_id", p["portfolio_id"]).eq("ticker", p["ticker"]).execute().data
        for r in rows:
            fd = fx_on(ser, r["date"])
            new_price = round(float(r["price"]) * fd, 4)
            new_shares = round(float(r["shares"]) / fe, 8)
            new_value = round(float(r["value"]) * fd / fe, 2)
            # daily_holdings PK is composite (portfolio_id, date, ticker)
            dh_updates.append((p["portfolio_id"], p["ticker"], r["date"],
                               new_shares, new_price, new_value))
        print(f"  {p['portfolio_id']:11} {p['ticker']:10} {len(rows)} rows")

    print(f"\nTotal: {len(pos_updates)} positions, {len(dh_updates)} daily_holdings rows")

    if not args.confirm:
        print("\nDRY RUN — nothing written. Re-run with --confirm to apply.")
        sys.exit(0)

    # ── WRITE ──
    for pid, tk, ccy, fe, sh, ep, un in pos_updates:
        sb.table("positions").update(
            {"shares": round(sh, 8), "entry_price": round(ep, 4), "units": un}
        ).eq("id", pid).execute()
    # daily_holdings: batched upsert (full rows on the composite PK) — far fewer
    # round-trips than 755 individual UPDATEs.
    dh_rows = [{"portfolio_id": pf, "date": d, "ticker": tk,
                "shares": sh, "price": pr, "value": val}
               for (pf, tk, d, sh, pr, val) in dh_updates]
    for i in range(0, len(dh_rows), 500):
        sb.table("daily_holdings").upsert(
            dh_rows[i:i + 500], on_conflict="portfolio_id,date,ticker"
        ).execute()

    # set the guard flag
    if flag:
        sb.table("settings").update({"value": "done"}).eq("key", MIGRATION_KEY).execute()
    else:
        sb.table("settings").insert({"key": MIGRATION_KEY, "value": "done"}).execute()

    print(f"\nDONE. {len(pos_updates)} positions + {len(dh_updates)} daily_holdings rows updated.")


if __name__ == "__main__":
    main()
