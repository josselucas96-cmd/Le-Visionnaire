"""Generate SQL INSERT statements for Le Bâtisseur v7 (26 positions).

Fetches entry prices for May 4, 2026 (first trading day after IPS inception May 2, Saturday).
Outputs SQL to scripts/insert_batisseur_v7.sql for review then execution in Supabase SQL editor.
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
import yfinance as yf
import pandas as pd

INCEPTION = "2026-05-06"  # User-confirmed: inception is today
ENTRY_PRICE_DATE = "2026-05-06"  # Today — fetcher picks latest available close
OUT_SQL = Path(r"c:\Users\USER\Desktop\Projet Claude\Claude Racine\Streamlit_project\scripts\insert_batisseur_v7.sql")

# (ticker, name, layer, weight%, gics_sector, geography, thematic, thesis_short)
POSITIONS = [
    # Obvious
    ("NVDA",    "NVIDIA",                  "Obvious",         8.0,  "Information Technology", "USA",          "AI / Semi",            "AI infrastructure leader, dominant GPU position with strong moat in accelerated computing."),
    ("CSU.TO",  "Constellation Software",  "Obvious",         7.0,  "Information Technology", "Canada",       "Software",             "Disciplined serial acquirer of vertical market software, exceptional capital allocation."),
    ("AMZN",    "Amazon",                  "Obvious",         6.0,  "Consumer Discretionary", "USA",          "Cloud",                "Multi-engine compounder: AWS, retail, advertising; best-in-class operational leverage."),
    ("META",    "Meta Platforms",          "Obvious",         6.0,  "Communication Services", "USA",          "Social Platform",      "Asymmetric AI capex bet, strong network effects across WhatsApp/Instagram/Facebook."),
    ("MELI",    "MercadoLibre",            "Obvious",         5.0,  "Consumer Discretionary", "LatAm",        "Consumer Growth",      "Latin America e-commerce + fintech ecosystem with structural demographic tailwind."),
    ("LLY",     "Eli Lilly",               "Obvious",         5.0,  "Healthcare",             "USA",          "Obesity",              "GLP-1 leader (Mounjaro/Zepbound) with broad pipeline across obesity, neuro, oncology."),
    ("JPM",     "JPMorgan Chase",          "Obvious",         4.5,  "Financials",             "USA",          "Fintech",              "Best-in-class capital allocation, scale advantage, technology investment paying off."),
    ("BABA",    "Alibaba",                 "Obvious",         4.0,  "Consumer Discretionary", "Asia ex-Japan","Consumer Growth",      "China e-commerce + cloud, accelerating buybacks, AI capex underappreciated."),
    # Haute Qualité
    ("MSFT",    "Microsoft",               "Haute Qualité",   4.0,  "Information Technology", "USA",          "Software",             "Office + Azure backbone, cloud + productivity dual-engine compounding."),
    ("V",       "Visa",                    "Haute Qualité",   4.0,  "Financials",             "USA",          "Fintech",              "Global payments network with structural moat and predictable free cash flow."),
    ("BSX",     "Boston Scientific",       "Haute Qualité",   4.0,  "Healthcare",             "USA",          "Healthcare Equipment", "Cardiology and electrophysiology leader, switching cost moat in implantable devices."),
    ("FICO",    "Fair Isaac",              "Haute Qualité",   3.0,  "Information Technology", "USA",          "Fintech",              "Credit scoring monopoly with network effects and pricing power."),
    ("VRSK",    "Verisk Analytics",        "Haute Qualité",   3.0,  "Industrials",            "USA",          "Software",             "Insurance data analytics monopoly with recurring revenue model."),
    ("ISRG",    "Intuitive Surgical",      "Haute Qualité",   3.0,  "Healthcare",             "USA",          "Healthcare Equipment", "Robotic surgery leader with razor-and-blade recurring revenue model."),
    ("ULTA",    "Ulta Beauty",             "Haute Qualité",   3.0,  "Consumer Discretionary", "USA",          "Consumer Growth",      "Hybrid prestige + mass beauty retail moat with strong loyalty program."),
    ("RACE",    "Ferrari",                 "Haute Qualité",   2.0,  "Consumer Discretionary", "Europe",       "Luxury",               "Iconic luxury brand with scarcity-driven pricing power and supply discipline."),
    ("RMS.PA",  "Hermès",                  "Haute Qualité",   2.0,  "Consumer Discretionary", "Europe",       "Luxury",               "Ultra-luxury brand with consistent pricing power and multi-generational moat."),
    # Diversification
    ("EL.PA",   "EssilorLuxottica",        "Diversification", 3.0,  "Healthcare",             "Europe",       "Healthcare Equipment", "Vertically integrated eyewear leader, smart glasses partnership with Meta."),
    ("WM",      "Waste Management",        "Diversification", 3.0,  "Industrials",            "USA",          "Other",                "Landfill regulatory monopoly with structural physical moat."),
    ("NVO",     "Novo Nordisk",            "Diversification", 3.0,  "Healthcare",             "Europe",       "Obesity",              "GLP-1 obesity franchise with attractive valuation post correction; pipeline optionality."),
    ("VICI",    "VICI Properties",         "Diversification", 2.0,  "Real Estate",            "USA",          "Other",                "Casino property REIT, regulatory moat, attractive yield, long-term triple-net leases."),
    ("IBE.MC",  "Iberdrola",               "Diversification", 2.0,  "Utilities",              "Europe",       "Energy Transition",    "Spanish utility with renewables exposure and regulated cash flows."),
    ("DPZ",     "Domino's Pizza",          "Diversification", 2.0,  "Consumer Discretionary", "USA",          "Consumer Growth",      "Asset-light franchise model, strong ROIC, technology-led ordering platform."),
    ("STZ",     "Constellation Brands",    "Diversification", 2.0,  "Consumer Staples",       "USA",          "Consumer Growth",      "Premium beer portfolio (Modelo, Corona) with brand strength and pricing power."),
    # Tactical
    ("ZM",      "Zoom",                    "Tactical",        2.0,  "Information Technology", "USA",          "Software",             "Anthropic stake creates substantial sum-of-parts value relative to current EV."),
    ("CRCL",    "Circle",                  "Tactical",        2.0,  "Financials",             "USA",          "Fintech",              "USDC stablecoin issuer with infrastructure moat in crypto rails."),
]


def fetch_entry_prices(positions, target_date: str):
    """Fetch the latest available close on or before target_date.
    Returns dict ticker -> price.
    """
    tickers = [p[0] for p in positions]
    target = pd.Timestamp(target_date)
    start = target - pd.Timedelta(days=5)  # buffer for non-trading days
    end = target + pd.Timedelta(days=2)
    prices = {}
    for ticker in tickers:
        try:
            data = yf.Ticker(ticker).history(
                start=start.strftime("%Y-%m-%d"),
                end=end.strftime("%Y-%m-%d"),
            )
            if not data.empty:
                # Normalize tz: yfinance returns tz-aware indices for some tickers
                idx = data.index
                if hasattr(idx, "tz") and idx.tz is not None:
                    idx = idx.tz_localize(None)
                idx_norm = pd.DatetimeIndex(idx).normalize()
                # Take the latest available close on or before target
                mask = idx_norm <= target
                if mask.any():
                    last_idx = int(mask.sum()) - 1  # last True position
                    price = float(data["Close"].values[last_idx])
                    used_date = idx_norm[last_idx].strftime("%Y-%m-%d")
                else:
                    price = float(data["Close"].iloc[-1])
                    used_date = idx_norm[-1].strftime("%Y-%m-%d")
                prices[ticker] = round(price, 4)
                print(f"  {ticker:8s} -> {price:.2f}  ({used_date})")
            else:
                print(f"  {ticker:8s} -> NO DATA")
                prices[ticker] = None
        except Exception as e:
            print(f"  {ticker:8s} -> ERROR: {type(e).__name__}: {str(e)[:80]}")
            prices[ticker] = None
    return prices


def sql_escape(s: str) -> str:
    return s.replace("'", "''")


def main():
    print(f"Fetching entry prices for {ENTRY_PRICE_DATE}...")
    prices = fetch_entry_prices(POSITIONS, ENTRY_PRICE_DATE)

    missing = [t for t, p in prices.items() if p is None]
    if missing:
        print(f"\n⚠ MISSING PRICES for: {missing}")
        print("Edit the SQL manually before executing.")

    lines = [
        f"-- Le Bâtisseur v7 — INSERT positions",
        f"-- Inception: {INCEPTION} (per IPS Finale)",
        f"-- Entry prices: {ENTRY_PRICE_DATE} closes",
        f"-- 26 positions, 94.5% invested, 5.5% cash, UCITS V compliant",
        f"",
        f"-- 1. Update portfolio metadata (inception date)",
        f"UPDATE portfolios SET inception_date = '{INCEPTION}' WHERE id = 'batisseur';",
        f"",
        f"-- 2. Safety: clear any prior positions for this portfolio",
        f"DELETE FROM positions WHERE portfolio_id = 'batisseur';",
        f"",
        f"-- 3. Insert 26 active positions",
        f"INSERT INTO positions (portfolio_id, ticker, name, layer, weight, entry_price, entry_date, sector, geography, thematic, thesis_short, is_active) VALUES",
    ]

    rows = []
    for ticker, name, layer, weight, sector, geo, thematic, thesis in POSITIONS:
        price = prices.get(ticker)
        price_sql = f"{price}" if price is not None else "NULL  -- TODO: fill in entry_price manually"
        rows.append(
            f"  ('batisseur', '{ticker}', '{sql_escape(name)}', '{layer}', "
            f"{weight}, {price_sql}, '{INCEPTION}', '{sector}', '{geo}', "
            f"'{thematic}', '{sql_escape(thesis)}', true)"
        )
    lines.append(",\n".join(rows) + ";")
    lines.append("")
    lines.append("-- Verify:")
    lines.append("-- SELECT count(*), sum(weight) FROM positions WHERE portfolio_id='batisseur' AND is_active=true;")
    lines.append("-- Expected: 26 positions, sum(weight) = 94.5")

    sql = "\n".join(lines)
    OUT_SQL.parent.mkdir(parents=True, exist_ok=True)
    OUT_SQL.write_text(sql, encoding="utf-8")

    print(f"\nSQL written to: {OUT_SQL}")
    print(f"Positions: {len(POSITIONS)}, Total weight: {sum(p[3] for p in POSITIONS):.1f}%")
    print(f"Cash buffer (not inserted in positions): 5.5%")


if __name__ == "__main__":
    main()
