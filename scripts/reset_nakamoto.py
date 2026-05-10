"""Reset Le Nakamoto to today's inception (2026-05-11).

Clears the existing positions + transactions, fetches today's closing
prices via yfinance, and emits a SQL file that rebuilds the portfolio
cleanly. Run the resulting SQL once in Supabase SQL Editor.
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
import yfinance as yf
import pandas as pd

INCEPTION = "2026-05-11"  # today — the real launch
OUT_SQL = Path(r"c:\Users\USER\Desktop\Projet Claude\Claude Racine\Streamlit_project\scripts\reset_nakamoto.sql")

# (ticker, name, layer, weight%, sector, geography, thematic, thesis_short)
POSITIONS = [
    # ── Anchor: structural core, large-cap DATs (75%) ──
    ("MSTR",     "Strategy",                  "Anchor",      27.0, "Tech",          "USA",   "Pure",
     "Standard reference of the BTC treasury universe: largest BTC stack, mature ATM + preferreds machinery, institutional shareholder base."),
    ("MTPLF",    "Metaplanet",                "Anchor",      23.0, "Communication", "Japan", "Pure",
     "Japanese MicroStrategy. Yen-debasement tailwind, aggressive ATM execution, smaller cap = higher per-share BTC accretion runway."),
    ("ASST",     "Strive Asset Management",   "Anchor",      15.0, "Finance",       "USA",   "Pure",
     "Strive post-Asset Entities merger. Vivek Ramaswamy's BTC treasury vehicle, distinct American capital pool and brand."),
    ("ALCPB.PA", "Capital B",                 "Anchor",      10.0, "Tech",          "Europe","Pure",
     "European BTC treasury leader (ex Blockchain Group), Euronext-listed, distinct EUR capital pool with same playbook."),
    # ── Exploratory: smaller caps, regional, more torque (21%) ──
    ("OBTC3.SA", "OranjeBTC",                 "Exploratory",  8.0, "Finance",       "LatAm", "Pure",
     "Brazil's largest listed BTC treasury, B3 listing — emerging-market BTC proxy with local currency debasement exposure."),
    # H100.OL is not on yfinance — fall back to the Frankfurt OTC line (GS9.F).
    # Same underlying company; this is the listing the live data already used.
    ("GS9.F",    "H100 Group",                "Exploratory",  7.0, "Healthcare",    "Europe","Hybrid",
     "Swedish medtech pivoted to BTC treasury. Nordic listing, distinct geography, hybrid balance sheet."),
    ("CASH3.SA", "Méliuz",                    "Exploratory",  3.0, "Consumer",      "LatAm", "Hybrid",
     "Brazilian fintech (cashback platform) with BTC treasury allocation. Hybrid operating business + BTC stack."),
    ("SWC.L",    "Smarter Web Company",       "Exploratory",  3.0, "Communication", "Europe","Pure",
     "UK web-services shell adopting an aggressive BTC treasury build. Small cap, high beta to BTC."),
    # ── Income: Bitcoin-backed preferreds (4%) ──
    ("STRC",     "Strategy STRC Preferred",   "Income",       4.0, "Finance",       "USA",   "Pure",
     "MSTR's perpetual preferred shares, ~11.5% annual coupon paid monthly. Bitcoin-backed yield instrument, decouples coupon from BTC spot."),
]


def fetch_entry_prices(positions, target_date: str):
    """Fetch latest closing price on or before target_date for each ticker."""
    tickers = [p[0] for p in positions]
    target = pd.Timestamp(target_date)
    start = target - pd.Timedelta(days=7)
    end = target + pd.Timedelta(days=2)
    prices = {}
    for ticker in tickers:
        try:
            data = yf.Ticker(ticker).history(
                start=start.strftime("%Y-%m-%d"),
                end=end.strftime("%Y-%m-%d"),
            )
            if not data.empty:
                idx = data.index
                if hasattr(idx, "tz") and idx.tz is not None:
                    idx = idx.tz_localize(None)
                idx_norm = pd.DatetimeIndex(idx).normalize()
                mask = idx_norm <= target
                if mask.any():
                    last_idx = int(mask.sum()) - 1
                    price = float(data["Close"].values[last_idx])
                    used_date = idx_norm[last_idx].strftime("%Y-%m-%d")
                else:
                    price = float(data["Close"].iloc[-1])
                    used_date = idx_norm[-1].strftime("%Y-%m-%d")
                prices[ticker] = round(price, 4)
                print(f"  {ticker:12s} -> {price:>10.2f}  ({used_date})")
            else:
                print(f"  {ticker:12s} -> NO DATA")
                prices[ticker] = None
        except Exception as e:
            print(f"  {ticker:12s} -> ERROR: {type(e).__name__}: {str(e)[:80]}")
            prices[ticker] = None
    return prices


def sql_escape(s: str) -> str:
    return s.replace("'", "''")


def main():
    print(f"Fetching entry prices for {INCEPTION}...")
    prices = fetch_entry_prices(POSITIONS, INCEPTION)

    missing = [t for t, p in prices.items() if p is None]
    if missing:
        print(f"\nWARN: missing prices for {missing} — leave NULL in SQL or fix manually.")

    lines = [
        f"-- Le Nakamoto — RESET to today's inception ({INCEPTION})",
        f"-- 9 positions, 100% invested (75% Anchor + 21% Exploratory + 4% Income overlay)",
        f"-- Entry prices: yfinance close on/before {INCEPTION}",
        f"",
        f"-- 1. Reset portfolio inception",
        f"UPDATE portfolios SET inception_date = '{INCEPTION}' WHERE id = 'nakamoto';",
        f"",
        f"-- 2. Clear prior positions + transactions (clean slate)",
        f"DELETE FROM transactions WHERE portfolio_id = 'nakamoto';",
        f"DELETE FROM positions    WHERE portfolio_id = 'nakamoto';",
        f"",
        f"-- 3. Insert the 9 launch positions",
        f"INSERT INTO positions (portfolio_id, ticker, name, layer, weight, entry_price, entry_date, sector, geography, thematic, thesis_short, is_active) VALUES",
    ]

    rows = []
    for ticker, name, layer, weight, sector, geo, thematic, thesis in POSITIONS:
        price = prices.get(ticker)
        price_sql = f"{price}" if price is not None else "NULL  -- TODO: fill manually (yfinance had no data)"
        rows.append(
            f"  ('nakamoto', '{ticker}', '{sql_escape(name)}', '{layer}', "
            f"{weight}, {price_sql}, '{INCEPTION}', '{sector}', '{geo}', "
            f"'{thematic}', '{sql_escape(thesis)}', true)"
        )
    lines.append(",\n".join(rows) + ";")
    lines.append("")
    lines.append("-- Verify:")
    lines.append("-- SELECT count(*), sum(weight), inception_date")
    lines.append("-- FROM positions p JOIN portfolios pf ON pf.id = p.portfolio_id")
    lines.append("-- WHERE p.portfolio_id = 'nakamoto' AND p.is_active = true")
    lines.append("-- GROUP BY inception_date;")
    lines.append("-- Expected: 9, 100, 2026-05-11")

    sql = "\n".join(lines)
    OUT_SQL.parent.mkdir(parents=True, exist_ok=True)
    OUT_SQL.write_text(sql, encoding="utf-8")

    print(f"\nSQL written to: {OUT_SQL}")
    print(f"Positions: {len(POSITIONS)}, total weight: {sum(p[3] for p in POSITIONS):.0f}%")
    if missing:
        print(f"WARN: {len(missing)} tickers without price — edit the SQL before running.")


if __name__ == "__main__":
    main()
