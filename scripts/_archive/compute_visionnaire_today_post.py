"""Computes Visionnaire portfolio value today using CURRENT DB state
(post-moves from today's rebalance 17h09)."""
from pathlib import Path

import toml
import yfinance as yf
from supabase import create_client


def main():
    secrets = toml.load(Path(__file__).parent / ".streamlit" / "secrets.toml")
    sb = create_client(secrets["supabase_url"], secrets["supabase_key"])

    positions = (
        sb.table("positions")
        .select("ticker, weight, entry_price, units")
        .eq("portfolio_id", "visionnaire")
        .eq("is_active", True)
        .order("weight", desc=True)
        .execute()
        .data
    )
    pf = sb.table("portfolios").select("cash_units").eq("id", "visionnaire").execute().data[0]
    cash_units = float(pf.get("cash_units") or 0)

    tickers = [p["ticker"] for p in positions]
    current = {}
    for t in tickers:
        try:
            current[t] = float(yf.Ticker(t).fast_info.last_price)
        except Exception as e:
            current[t] = None

    print(f"{'Ticker':<7} {'Weight':>7} {'PRU':>10} {'Today':>10} {'Return%':>10} {'Value':>8}")
    print("-" * 60)
    total_w = 0.0
    total_value = 0.0
    for p in positions:
        cur = current.get(p["ticker"])
        w = float(p["weight"])
        pru = float(p["entry_price"])
        total_w += w
        if cur is None:
            print(f"{p['ticker']:<7} {w:>7.2f} {pru:>10.4f} {'-':>10} {'-':>10} {'-':>8}")
            continue
        ret = (cur - pru) / pru * 100
        val = w * cur / pru
        total_value += val
        print(f"{p['ticker']:<7} {w:>7.2f} {pru:>10.4f} {cur:>10.2f} {ret:>+9.2f}% {val:>7.2f}")

    nav = total_value + cash_units
    cash_drift = cash_units / nav * 100
    print("-" * 60)
    print(f"Sum positions weight (cost basis): {total_w:.4f}")
    print(f"Cash units (DB):                   {cash_units:.4f}")
    print(f"Sum positions value:               {total_value:.4f}")
    print(f"TOTAL NAV:                         {nav:.4f}")
    print(f"Cash drifted %:                    {cash_drift:.2f}%")
    print(f"\nInception perf: {nav - 100:+.2f}%")


if __name__ == "__main__":
    main()
