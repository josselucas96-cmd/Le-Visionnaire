"""Phase B — Backfill daily_holdings (+ positions.shares + portfolios.cash_amount)
for all 3 portfolios using transactions log + initial snapshot CSV + yfinance.

Strategy (event sourcing from transactions log):
- Start with cash = initial_capital ($), shares = {} (empty).
- Replay transactions in chronological order, updating shares & cash.
- For each trading day from inception to today: snapshot the (shares, cash) state
  after applying that day's transactions, valued at yfinance daily close.

Idempotent: re-runnable safely (uses UPSERT).

Math:
- IN  (buy/reinforce): shares_added = weight_in × initial_capital / 100 / price_in
                       cash -= shares_added × price_in  (= weight_in × initial_capital / 100)
- TRIM: shares_sold = weight_out × initial_capital / 100 / entry_price_out
        cash += shares_sold × price_out  (real proceeds at exit price)
- OUT (close): shares_sold = current shares of ticker_out
               cash += shares_sold × price_out
               shares[ticker_out] = 0
- SWITCH: close ticker_out + open ticker_in (combination)
- DRIP/SPLIT: future, not in current data

Run from Streamlit_project/. Throwaway after Phase D cutover.
"""
import csv
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import toml
import yfinance as yf
from supabase import create_client


# ── Config ───────────────────────────────────────────────────────────────────
DEFAULT_INITIAL_CAPITAL = 1_000_000.0


def get_initial_capital(sb, portfolio_id: str) -> float:
    """Read initial_capital_<pid> setting, fallback to legacy 'initial_capital'
    for Visionnaire, then default to $1M."""
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
    return DEFAULT_INITIAL_CAPITAL


def fetch_yfinance_history(tickers, start_date, end_date):
    """Batched yfinance.download for all tickers."""
    df = yf.download(list(tickers), start=start_date, end=end_date,
                     auto_adjust=True, progress=False)
    if df.empty:
        return df
    if isinstance(df.columns, pd.MultiIndex):
        df = df["Close"]
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    df.index = pd.to_datetime(df.index.date)
    return df


def apply_transaction(txn, shares, cash, initial_capital):
    """Apply one transaction in-place to (shares dict, cash float).
    Returns (shares, cash) updated."""
    action = txn["action"]
    if action == "IN":
        # Buy or reinforce
        ticker = txn["ticker_in"]
        weight_in = float(txn.get("weight_in") or 0)
        price_in = float(txn.get("price_in") or 0)
        if weight_in <= 0 or price_in <= 0:
            return shares, cash
        dollar_amount = weight_in * initial_capital / 100.0
        shares_added = dollar_amount / price_in
        shares[ticker] = shares.get(ticker, 0.0) + shares_added
        cash -= dollar_amount
    elif action == "TRIM":
        ticker = txn["ticker_out"]
        weight_out = float(txn.get("weight_out") or 0)
        entry_price_out = float(txn.get("entry_price_out") or 0)
        price_out = float(txn.get("price_out") or 0)
        if weight_out <= 0 or entry_price_out <= 0 or price_out <= 0:
            return shares, cash
        # Shares sold based on cost basis released
        dollar_cost_released = weight_out * initial_capital / 100.0
        shares_sold = dollar_cost_released / entry_price_out
        if ticker in shares:
            shares[ticker] = max(0.0, shares[ticker] - shares_sold)
        # Real cash proceeds at exit price
        cash += shares_sold * price_out
    elif action == "OUT":
        ticker = txn["ticker_out"]
        price_out = float(txn.get("price_out") or 0)
        if ticker in shares and price_out > 0:
            cash += shares[ticker] * price_out
            shares[ticker] = 0.0
    elif action == "SWITCH":
        # Close ticker_out + open ticker_in
        ticker_out = txn["ticker_out"]
        ticker_in = txn["ticker_in"]
        price_out = float(txn.get("price_out") or 0)
        price_in = float(txn.get("price_in") or 0)
        weight_in = float(txn.get("weight_in") or 0)
        if ticker_out in shares and price_out > 0:
            cash += shares[ticker_out] * price_out
            shares[ticker_out] = 0.0
        if weight_in > 0 and price_in > 0:
            dollar_amount = weight_in * initial_capital / 100.0
            shares_added = dollar_amount / price_in
            shares[ticker_in] = shares.get(ticker_in, 0.0) + shares_added
            cash -= dollar_amount
    elif action == "DRIP":
        # Dividend reinvested: shares += dividend / reinvest_price
        ticker = txn["ticker_in"]
        weight_in = float(txn.get("weight_in") or 0)  # = cash_received
        price_in = float(txn.get("price_in") or 0)
        if ticker in shares and weight_in > 0 and price_in > 0:
            shares_added = weight_in * initial_capital / 100.0 / price_in
            shares[ticker] += shares_added
            # DRIP cash-neutral: cash inchangé
    elif action == "SPLIT":
        # Not implemented yet — would need ratio in reason or new column
        pass
    return shares, cash


def backfill_portfolio(sb, portfolio_id):
    """Backfill daily_holdings + positions.shares + portfolios.cash_amount.

    Bootstrap strategy: read position_snapshots WHERE snapshot_type='initial'
    at inception_date (created by Phase A SQL or earlier scripts). Then apply
    transactions logged AFTER inception_date.
    """
    pf = sb.table("portfolios").select("*").eq("id", portfolio_id).execute().data
    if not pf:
        print(f"  {portfolio_id}: not found, skip")
        return
    pf = pf[0]
    inception = pf["inception_date"]
    initial_capital = get_initial_capital(sb, portfolio_id)
    print(f"\n--- {portfolio_id} | inception {inception} | capital ${initial_capital:,.0f} ---")

    # Bootstrap shares + cash from initial snapshot CSV (git-tracked source of truth)
    csv_path = Path(__file__).parent / "snapshots" / portfolio_id / f"{inception}.csv"
    if not csv_path.exists():
        print(f"  WARNING: no CSV snapshot at {csv_path}, skip")
        return

    shares = {}
    total_weight = 0.0
    with open(csv_path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            ticker = r["ticker"]
            weight = float(r["weight"])
            entry_price = float(r["entry_price"])
            # shares = weight x capital / 100 / PRU
            sh = (weight * initial_capital / 100.0) / entry_price if entry_price > 0 else 0
            if sh > 0.0001:
                shares[ticker] = sh
            total_weight += weight
    cash = initial_capital * (100.0 - total_weight) / 100.0
    print(f"  Bootstrap from CSV: {len(shares)} positions, init cash ${cash:,.2f} ({100-total_weight:.2f}% of capital)")

    # Transactions AFTER inception_date only (we already have state at inception)
    txns = (
        sb.table("transactions")
        .select("*")
        .eq("portfolio_id", portfolio_id)
        .gt("date", inception)
        .order("date")
        .order("id")
        .execute()
        .data
    )
    print(f"  Transactions after inception: {len(txns)}")

    txns_by_date = defaultdict(list)
    for t in txns:
        txns_by_date[t["date"]].append(t)

    # All tickers we might need price history for (snapshot + any new from transactions)
    tickers = set(shares.keys())
    for t in txns:
        if t.get("ticker_in"):
            tickers.add(t["ticker_in"])
        if t.get("ticker_out"):
            tickers.add(t["ticker_out"])

    today = date.today()
    # Fetch a few days before inception so we can detect the previous trading day (T-1)
    fetch_start = (pd.Timestamp(inception) - pd.Timedelta(days=7)).date().isoformat()
    history = fetch_yfinance_history(tickers, fetch_start, (today + timedelta(days=1)).isoformat())
    if history.empty:
        print(f"  ERROR: yfinance returned empty history for {portfolio_id}")
        return

    # Determine T-1 = last trading day strictly before inception_date.
    # Used to add a single CASH anchor row at T-1 representing "capital deposited
    # the previous trading day evening, ready to invest at the next open".
    inception_ts = pd.Timestamp(inception)
    pre_inception_days = history.index[history.index < inception_ts]
    if len(pre_inception_days) > 0:
        t_minus_1 = pre_inception_days[-1].date().isoformat()
    else:
        t_minus_1 = None

    # Restrict trading_days to inception_date onwards (we don't need pre-inception
    # rows for positions — only the single T-1 CASH anchor).
    history_post = history[history.index >= inception_ts]
    print(f"  yfinance history: {history_post.shape[0]} trading days x {history_post.shape[1]} tickers (T-1 anchor: {t_minus_1})")

    rows_to_upsert = []

    # Insert the T-1 anchor row (CASH-only, NAV = initial_capital)
    if t_minus_1:
        rows_to_upsert.append({
            "portfolio_id": portfolio_id,
            "date":         t_minus_1,
            "ticker":       "CASH",
            "shares":       round(initial_capital, 2),
            "price":        1.0,
            "value":        round(initial_capital, 2),
        })

    trading_days = sorted(history_post.index)

    for ts in trading_days:
        date_str = ts.date().isoformat()
        # Apply all transactions for this date (in id order). The bootstrap
        # already set the state at inception, so we apply ALL transactions after
        # inception including those on inception+0 (none for now, future-proof).
        if date_str in txns_by_date:
            for t in txns_by_date[date_str]:
                shares, cash = apply_transaction(t, shares, cash, initial_capital)
        # Snapshot per ticker (skip zero/closed)
        for ticker, sh in shares.items():
            if sh <= 0.0001:
                continue
            if ticker not in history.columns:
                continue
            price = history.loc[ts, ticker] if ts in history.index else None
            if price is None or pd.isna(price):
                continue
            price = float(price)
            value = sh * price
            rows_to_upsert.append({
                "portfolio_id": portfolio_id,
                "date": date_str,
                "ticker": ticker,
                "shares": round(sh, 8),
                "price": round(price, 4),
                "value": round(value, 2),
            })
        # Cash row
        rows_to_upsert.append({
            "portfolio_id": portfolio_id,
            "date": date_str,
            "ticker": "CASH",
            "shares": round(cash, 2),
            "price": 1.0,
            "value": round(cash, 2),
        })

    final_shares = dict(shares)
    final_cash = cash
    nav_final = sum(s * float(history[t].dropna().iloc[-1]) for t, s in final_shares.items()
                    if s > 0.0001 and t in history.columns) + final_cash

    print(f"  Final state: cash=${final_cash:,.2f}  positions={len([s for s in final_shares.values() if s > 0.0001])}  NAV=${nav_final:,.2f}")
    print(f"  Rows to upsert into daily_holdings: {len(rows_to_upsert)}")

    return {
        "portfolio_id": portfolio_id,
        "rows": rows_to_upsert,
        "final_shares": final_shares,
        "final_cash": final_cash,
        "nav_final": nav_final,
        "initial_capital": initial_capital,
    }


def main():
    secrets = toml.load(Path(__file__).parent / ".streamlit" / "secrets.toml")
    sb = create_client(secrets["supabase_url"], secrets["supabase_key"])

    results = []
    for pid in ("visionnaire", "batisseur", "nakamoto"):
        result = backfill_portfolio(sb, pid)
        if result:
            results.append(result)

    print("\n" + "=" * 70)
    print("SUMMARY (dry run — nothing written yet)")
    print("=" * 70)
    for r in results:
        print(f"  {r['portfolio_id']:<12} NAV=${r['nav_final']:>14,.2f}  perf={(r['nav_final']/r['initial_capital']-1)*100:>+7.2f}%  rows={len(r['rows']):>5}")

    answer = input("\nApply (upsert daily_holdings + update positions.shares + portfolios.cash_amount)? [y/N]: ").strip().lower()
    if answer != "y":
        print("Aborted. Nothing written.")
        return

    print("\nWriting...")
    for r in results:
        # daily_holdings UPSERT in chunks
        CHUNK = 200
        rows = r["rows"]
        for i in range(0, len(rows), CHUNK):
            sb.table("daily_holdings").upsert(
                rows[i:i + CHUNK], on_conflict="portfolio_id,date,ticker"
            ).execute()
        print(f"  {r['portfolio_id']}: {len(rows)} rows upserted in daily_holdings")

        # positions.shares update — final cumulative state
        positions = (
            sb.table("positions")
            .select("id, ticker, is_active")
            .eq("portfolio_id", r["portfolio_id"])
            .execute()
            .data
        )
        for p in positions:
            sh = r["final_shares"].get(p["ticker"], 0.0)
            sb.table("positions").update({"shares": round(sh, 8)}).eq("id", p["id"]).execute()
        print(f"  {r['portfolio_id']}: positions.shares updated for {len(positions)} rows")

        # portfolios.cash_amount
        sb.table("portfolios").update({
            "cash_amount": round(r["final_cash"], 2),
        }).eq("id", r["portfolio_id"]).execute()
        print(f"  {r['portfolio_id']}: portfolios.cash_amount = ${r['final_cash']:,.2f}")

    print("\nDone.")


if __name__ == "__main__":
    main()
