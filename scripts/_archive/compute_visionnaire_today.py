"""Computes Visionnaire portfolio value today using INITIAL state from snapshot
(as if no moves had been made since April 13)."""
import csv
from pathlib import Path

import yfinance as yf


def main():
    csv_path = Path(__file__).parent / "snapshots" / "visionnaire" / "2026-04-13.csv"
    positions = []
    with open(csv_path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            positions.append({
                "ticker":      r["ticker"],
                "weight":      float(r["weight"]),
                "entry_price": float(r["entry_price"]),
            })

    tickers = [p["ticker"] for p in positions]
    print(f"Fetching current prices for {len(tickers)} tickers...")
    current = {}
    for t in tickers:
        try:
            info = yf.Ticker(t).fast_info
            current[t] = float(info.last_price)
        except Exception as e:
            print(f"  {t}: ERROR {e}")
            current[t] = None

    print()
    print(f"{'Ticker':<7} {'Weight':>7} {'PRU':>10} {'Today':>10} {'Return%':>10} {'Value':>8}")
    print("-" * 60)
    total_w = sum(p["weight"] for p in positions)
    total_value = 0.0
    for p in positions:
        cur = current.get(p["ticker"])
        if cur is None:
            print(f"{p['ticker']:<7} {p['weight']:>7.2f} {p['entry_price']:>10.2f} {'—':>10} {'—':>10} {'—':>8}")
            continue
        ret = (cur - p["entry_price"]) / p["entry_price"] * 100
        val = p["weight"] * cur / p["entry_price"]
        total_value += val
        print(f"{p['ticker']:<7} {p['weight']:>7.2f} {p['entry_price']:>10.2f} {cur:>10.2f} {ret:>+9.2f}% {val:>7.2f}")

    cash = 100.0 - total_w
    nav = total_value + cash
    print("-" * 60)
    print(f"{'Σ positions':<24} {'':>10} {'':>10} {'':>10} {total_value:>7.2f}")
    print(f"{'Cash (static)':<24} {'':>10} {'':>10} {'':>10} {cash:>7.2f}")
    print(f"{'TOTAL NAV':<24} {'':>10} {'':>10} {'':>10} {nav:>7.2f}")
    print(f"\nInception perf: {nav - 100:+.2f}%")


if __name__ == "__main__":
    main()
