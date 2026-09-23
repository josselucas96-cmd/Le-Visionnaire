# -*- coding: utf-8 -*-
"""Explain a month's gap to the benchmark, before writing the report commentary.

    python scripts/explain_month.py batisseur:2026-06 nakamoto:2026-08
    python scripts/explain_month.py --month 2026-09          # every public portfolio

For each portfolio-month it prints, read-only:
  * the portfolio and benchmark returns over the SAME window (from the T-1 anchor
    in the inception month, from the previous month-end otherwise);
  * every holding's weight at the start, return, contribution and ACTIVE
    contribution, i.e. weight x (return - benchmark return): the positions that
    made the gap, in percentage points;
  * the same grouped by sector;
  * for equity benchmarks, the month's SPDR sector returns and the largest
    index constituents, flagged when the portfolio does not hold them.

The commentary then names the positions behind the gap with the verified reason
for each move.
"""
import argparse
import os
import sys
import warnings

warnings.filterwarnings("ignore")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import pandas as pd
import toml
import yfinance as yf
from supabase import create_client

sec = toml.load(os.path.join(".streamlit", "secrets.toml"))
sb = create_client(sec["supabase_url"], sec["supabase_key"])

SPLIT_RATIOS = (2, 3, 4, 5, 6, 8, 10, 20, 25, 50, 100)
SECTOR_ETF = {"XLK": "Tech", "XLF": "Financials", "XLV": "Health Care", "XLY": "Cons. Disc.",
              "XLC": "Comm. Svcs", "XLI": "Industrials", "XLE": "Energy", "XLP": "Staples",
              "XLU": "Utilities", "XLB": "Materials", "XLRE": "Real Estate"}
MEGA = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "AVGO", "TSLA", "COST", "NFLX", "PLTR", "AMD"]


def is_split(share_ratio, value_ratio):
    """Same rule as generate_monthly_report._looks_like_split."""
    if abs(value_ratio - 1) > 0.30:
        return False
    return any(abs(share_ratio - r) / r < 0.02 or abs(share_ratio - 1 / r) * r < 0.02 for r in SPLIT_RATIOS)


def ledger(pid, a, b):
    rows, off = [], 0
    while True:
        chunk = (sb.table("daily_holdings").select("date,ticker,shares,price,value").eq("portfolio_id", pid)
                 .gte("date", a).lte("date", b).order("date").order("ticker")
                 .range(off, off + 999).execute().data)
        rows += chunk
        if len(chunk) < 1000:
            return rows
        off += 1000


_PX = {}


def closes(tickers, a, b):
    key = (tuple(sorted(tickers)), a, b)
    if key not in _PX:
        d = yf.download(list(tickers), start=(pd.Timestamp(a) - pd.Timedelta(days=7)).date().isoformat(),
                        end=(pd.Timestamp(b) + pd.Timedelta(days=1)).date().isoformat(),
                        auto_adjust=True, progress=False)["Close"]
        if isinstance(d, pd.Series):
            d = d.to_frame(tickers[0])
        d.index = pd.to_datetime(d.index.date)
        _PX[key] = d
    return _PX[key]


def ret(series, a, b):
    s = series.dropna()
    s0, s1 = s[s.index <= pd.Timestamp(a)], s[s.index <= pd.Timestamp(b)]
    if s0.empty or s1.empty:
        return None
    return (float(s1.iloc[-1]) / float(s0.iloc[-1]) - 1) * 100


def build_cases(targets):
    """[(pid, benchmark, window_start, window_end)] for 'pid:YYYY-MM' targets."""
    out = []
    for t in targets:
        pid, ym = t.split(":")
        pf = sb.table("portfolios").select("*").eq("id", pid).execute().data[0]
        end = (pd.Timestamp(ym + "-01") + pd.offsets.MonthEnd(0)).date().isoformat()
        start = (pd.Timestamp(ym + "-01") - pd.Timedelta(days=1)).date().isoformat()
        anchor = (sb.table("daily_holdings").select("date").eq("portfolio_id", pid)
                  .order("date").limit(1).execute().data[0]["date"])
        out.append((pid, pf["benchmark_primary"], max(start, anchor), end))
    return out


def explain(pid, bench, a, b, sectors):
    df = pd.DataFrame(ledger(pid, a, b))
    df["value"] = df["value"].astype(float)
    nav = df.groupby("date")["value"].sum()
    nav0, nav1 = float(nav.iloc[0]), float(nav.iloc[-1])
    pr = (nav1 / nav0 - 1) * 100
    br = ret(closes([bench], a, b)[bench], a, b)
    print(f"\n{'=' * 100}\n{pid.upper()} {b[:7]}   portfolio {pr:+.2f}%   {bench} {br:+.2f}%   "
          f"gap {pr - br:+.2f}pp   (window {a} -> {b})")

    out = []
    for tk, g in df[df.ticker != "CASH"].groupby("ticker"):
        recs = g.sort_values("date").to_dict("records")
        flow, sf = 0.0, 1.0
        for p0, p1 in zip(recs, recs[1:]):
            s0, s1, q0, q1 = float(p0["shares"]), float(p1["shares"]), float(p0["price"]), float(p1["price"])
            if s0 <= 0 or q0 <= 0 or abs(s1 - s0) < 1e-9:
                continue
            if is_split(s1 / s0, s1 * q1 / (s0 * q0)):
                sf *= s1 / s0
            else:
                flow += (s1 - s0) * q1
        opened = recs[0]["date"] != a
        held_end = recs[-1]["date"] == b
        v0 = 0.0 if opened else float(recs[0]["value"])
        v1 = float(recs[-1]["value"]) if held_end else 0.0
        if not held_end:
            flow -= float(recs[-1]["value"])
        if opened:
            flow += float(recs[0]["value"])
        pnl = v1 - v0 - flow
        w0 = v0 / nav0 * 100
        r_i = (float(recs[-1]["price"]) / (float(recs[0]["price"]) / sf) - 1) * 100
        out.append(dict(tk=tk, sector=sectors.get(tk) or "?", w0=w0, r=r_i, contrib=pnl / nav0 * 100,
                        active=pnl / nav0 * 100 - w0 / 100 * br,
                        status="opened" if opened else ("sold" if not held_end else "held")))

    cash_w = float(df[(df.ticker == "CASH") & (df.date == a)]["value"].sum()) / nav0 * 100
    t = pd.DataFrame(out).sort_values("active")
    print(f"  cash at start {cash_w:.1f}%  -> effect vs benchmark {-cash_w / 100 * br:+.2f}pp")
    print("  HOLDINGS, worst to best active contribution:")
    for _, r in t.iterrows():
        print(f"     {r.tk:<9} {r.sector[:22]:<22} w0 {r.w0:5.1f}%  ret {r.r:+7.2f}%  "
              f"contrib {r.contrib:+6.2f}  active {r.active:+6.2f}  [{r.status}]")
    print("  BY SECTOR:")
    for s_, r in t.groupby("sector").agg(w0=("w0", "sum"), contrib=("contrib", "sum"),
                                         active=("active", "sum")).sort_values("active").iterrows():
        print(f"     {s_[:28]:<28} w0 {r.w0:5.1f}%  contrib {r.contrib:+6.2f}  active {r.active:+6.2f}")

    if bench in ("SPY", "QQQ"):
        etf = closes(list(SECTOR_ETF), a, b)
        srt = sorted(((SECTOR_ETF[k], ret(etf[k], a, b)) for k in SECTOR_ETF), key=lambda x: -(x[1] or -99))
        print("  INDEX SECTORS (SPDR ETFs): " + ", ".join(f"{n} {v:+.1f}%" for n, v in srt))
        mg = closes(MEGA, a, b)
        held = set(t.tk)
        print("  LARGE CAPS: " + ", ".join(f"{m}{'*' if m in held else ''} {ret(mg[m], a, b):+.1f}%" for m in MEGA)
              + "   (* = held)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("targets", nargs="*", help="portfolio:YYYY-MM")
    ap.add_argument("--month", help="YYYY-MM, for every active public portfolio")
    args = ap.parse_args()
    targets = list(args.targets)
    if args.month:
        targets += [f"{p['id']}:{args.month}"
                    for p in sb.table("portfolios").select("id,is_active").execute().data
                    if p.get("is_active") and p["id"] != "test"]
    if not targets:
        ap.error("give portfolio:YYYY-MM targets or --month")
    for pid, bench, a, b in build_cases(targets):
        sectors = {p["ticker"]: p.get("sector")
                   for p in sb.table("positions").select("ticker,sector").eq("portfolio_id", pid).execute().data}
        explain(pid, bench, a, b, sectors)


if __name__ == "__main__":
    main()
