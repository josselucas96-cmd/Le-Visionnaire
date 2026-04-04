"""
Admin Cockpit — password protected.
Only you should access this page. It lets you add/close positions and manage settings.
"""
import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import date

from utils.data import (
    get_positions, get_transactions,
    add_position, close_position, trim_position, switch_position,
    get_setting, upsert_setting,
)
from utils.market import get_prices

st.set_page_config(page_title="Cockpit | Admin", layout="wide")

# ── Auth ──────────────────────────────────────────────────────────────────────
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("Admin Access")
    pwd = st.text_input("Password", type="password")
    if st.button("Login", type="primary"):
        if pwd == st.secrets.get("admin_password", ""):
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Incorrect password")
    st.stop()

# ── Cockpit ───────────────────────────────────────────────────────────────────
col_title, col_logout = st.columns([8, 1])
with col_title:
    st.title("Cockpit")
with col_logout:
    if st.button("Logout"):
        st.session_state.authenticated = False
        st.rerun()

# ── Settings ──────────────────────────────────────────────────────────────────
with st.expander("Portfolio Settings"):
    c1, c2 = st.columns(2)
    with c1:
        inc = st.text_input("Inception Date (YYYY-MM-DD)",
                            value=get_setting("inception_date", "2026-04-01"))
    with c2:
        name = st.text_input("Portfolio Name",
                             value=get_setting("portfolio_name", "Le Visionnaire"))
    if st.button("Save Settings"):
        upsert_setting("inception_date", inc)
        upsert_setting("portfolio_name", name)
        st.success("Saved.")
        st.cache_data.clear()

st.divider()

# ── Active positions ──────────────────────────────────────────────────────────
positions = get_positions()
st.subheader(f"Active Positions ({len(positions)})")

if positions:
    tickers_live = tuple(p["ticker"] for p in positions)
    prices_live  = get_prices(tickers_live)
    for p in positions:
        live = prices_live.get(p["ticker"], {})
        p["current_price"] = live.get("price")
        p["change_today"]  = live.get("change_pct")
        if p["current_price"] and p["entry_price"]:
            p["perf_pct"] = round(
                (p["current_price"] - p["entry_price"]) / p["entry_price"] * 100, 2
            )
        else:
            p["perf_pct"] = None

    df_pos = pd.DataFrame(positions)
    total_weight = df_pos["weight"].sum()
    st.caption(f"Total weight: **{total_weight:.1f}%** (target: 100%)")

    display_cols = [c for c in [
        "ticker", "name", "weight", "entry_price", "current_price",
        "perf_pct", "change_today", "entry_date",
        "sector", "geography", "thematic", "thesis_short"
    ] if c in df_pos.columns]

    display_admin = df_pos[display_cols].rename(columns={
        "ticker": "Ticker", "name": "Name", "weight": "Weight %",
        "entry_price": "Entry", "current_price": "Price",
        "perf_pct": "Perf %", "change_today": "Today %",
        "entry_date": "Entry Date", "sector": "Sector",
        "geography": "Geography", "thematic": "Thematic", "thesis_short": "Thesis",
    })

    cash_pct = round(max(0.0, 100.0 - total_weight), 1)
    if cash_pct <= 0 or cash_pct >= 10:
        cash_color = "#FF4B4B"
    elif cash_pct <= 2 or cash_pct >= 8:
        cash_color = "#FFA500"
    else:
        cash_color = "#00D09C"

    def color_signed_admin(col):
        return [
            "color: #00D09C" if isinstance(v, (int, float)) and v > 0
            else "color: #FF4B4B" if isinstance(v, (int, float)) and v < 0
            else "" for v in col
        ]

    styled = display_admin.style.format({
        "Weight %": lambda v: f"{v:.1f}%" if isinstance(v, (int, float)) else "",
        "Entry":    lambda v: f"{v:.2f}" if isinstance(v, (int, float)) else "",
        "Price":    lambda v: f"{v:.2f}" if isinstance(v, (int, float)) else "",
        "Perf %":   lambda v: f"{v:+.2f}%" if isinstance(v, (int, float)) else "",
        "Today %":  lambda v: f"{v:+.2f}%" if isinstance(v, (int, float)) else "",
    }).apply(color_signed_admin, subset=["Perf %", "Today %"])

    st.dataframe(styled, use_container_width=True, hide_index=True)
    st.markdown(
        f"<span style='color:{cash_color}; font-weight:600;'>CASH (USD) — {cash_pct:.1f}%</span>",
        unsafe_allow_html=True,
    )
else:
    st.info("No active positions.")

st.divider()

SECTORS    = ["Tech", "Healthcare", "Consumer", "Finance", "Communication",
              "Industrials", "Energy", "Materials", "Real Estate", "Utilities"]
GEOS       = ["USA", "Europe", "Japan", "Asia ex-Japan", "LatAm", "Global", "Other"]
THEMATICS  = ["AI / Semi", "DAT / Bitcoin", "Biotech / Genomics", "Space / Defense",
              "Robotics / Automation", "Fintech / Payments", "Consumer Growth",
              "Energy Transition", "Software / SaaS", "Other"]

pos_options = {f"{p['ticker']}  —  {p['name']}": p for p in positions}

tab_add, tab_close, tab_switch, tab_history = st.tabs([
    "➕  Add", "✖  Close", "🔄  Switch", "📋  History"
])

# ── ADD ───────────────────────────────────────────────────────────────────────
# Exchange label → Yahoo Finance suffix (empty = US)
EXCHANGES = {
    "Auto-detect":          None,
    "NYSE / NASDAQ (US)":   "",
    "Paris (FR)":           ".PA",
    "Milan (IT)":           ".MI",
    "London (UK)":          ".L",
    "Frankfurt (DE)":       ".DE",
    "Amsterdam (NL)":       ".AS",
    "Zurich (CH)":          ".SW",
    "Stockholm (SE)":       ".ST",
    "Oslo (NO)":            ".OL",
    "Madrid (ES)":          ".MC",
    "Brussels (BE)":        ".BR",
    "Lisbon (PT)":          ".LS",
    "Helsinki (FI)":        ".HE",
    "Copenhagen (DK)":      ".CO",
    "Tokyo (JP)":           ".T",
    "Hong Kong":            ".HK",
    "Toronto (CA)":         ".TO",
    "Sydney (AU)":          ".AX",
}
EXCHANGE_AUTODETECT_SUFFIXES = [
    "", ".PA", ".MI", ".L", ".DE", ".AS", ".SW",
    ".ST", ".OL", ".CO", ".HE", ".BR", ".LS", ".MC", ".AT",
    ".T", ".HK", ".TO", ".AX",
]

def _valid_info(info):
    name  = info.get("longName") or info.get("shortName") or ""
    price = info.get("currentPrice") or info.get("regularMarketPrice") or 0.0
    return bool(name) and not name.strip().isdigit() and float(price) > 0

def resolve_ticker(raw, suffix):
    """If suffix is given, use it directly. Otherwise auto-detect."""
    if suffix is not None:
        t    = raw + suffix
        info = yf.Ticker(t).info
        return t, info
    for s in EXCHANGE_AUTODETECT_SUFFIXES:
        t    = raw + s
        info = yf.Ticker(t).info
        if _valid_info(info):
            return t, info
    return raw, {}

SECTOR_MAP = {
    "Technology": "Tech", "Consumer Cyclical": "Consumer",
    "Consumer Defensive": "Consumer", "Healthcare": "Healthcare",
    "Financial Services": "Finance", "Communication Services": "Communication",
    "Industrials": "Industrials", "Energy": "Energy",
    "Basic Materials": "Materials", "Real Estate": "Real Estate",
    "Utilities": "Utilities",
}
GEO_MAP = {
    "United States": "USA", "Japan": "Japan",
    "United Kingdom": "Europe", "France": "Europe", "Germany": "Europe",
    "Netherlands": "Europe", "Sweden": "Europe", "Switzerland": "Europe",
    "Italy": "Europe", "Spain": "Europe", "Norway": "Europe",
    "China": "Asia ex-Japan", "Hong Kong": "Asia ex-Japan",
    "South Korea": "Asia ex-Japan", "Taiwan": "Asia ex-Japan",
    "India": "Asia ex-Japan", "Singapore": "Asia ex-Japan",
    "Brazil": "LatAm", "Mexico": "LatAm", "Argentina": "LatAm",
}

with tab_add:
    existing_w = sum(p["weight"] for p in positions)
    remaining  = round(max(0, 100 - existing_w), 1)
    st.caption(f"Invested: **{existing_w:.1f}%** · Available (cash): **{remaining:.1f}%**")

    # Ticker lookup (outside the form so it can trigger a rerun)
    lk1, lk2, lk3 = st.columns([2, 2, 1])
    with lk1:
        lookup_ticker = st.text_input("Ticker", key="lookup_ticker",
                                      placeholder="e.g. TSLA, MC, ENI").strip().upper()
    with lk2:
        exchange_label = st.selectbox("Exchange (optional)", list(EXCHANGES.keys()), key="lookup_exchange")
    with lk3:
        st.write("")
        st.write("")
        do_lookup = st.button("Lookup", type="secondary")

    if do_lookup:
        if lookup_ticker:
            suffix = EXCHANGES[exchange_label]
            try:
                with st.spinner(f"Fetching {lookup_ticker}…"):
                    resolved, info = resolve_ticker(lookup_ticker, suffix)
                if _valid_info(info):
                    st.session_state["af_ticker"]   = resolved
                    st.session_state["af_name"]     = info.get("longName") or info.get("shortName") or ""
                    st.session_state["af_sector"]   = SECTOR_MAP.get(info.get("sector", ""), "")
                    st.session_state["af_geo"]      = GEO_MAP.get(info.get("country", ""), "Other")
                    price = info.get("currentPrice") or info.get("regularMarketPrice") or 0.0
                    st.session_state["af_price"]    = float(price)
                    if resolved != lookup_ticker:
                        st.info(f"Resolved as **{resolved}** — {st.session_state['af_name']}")
                else:
                    st.warning(f"'{lookup_ticker}' not found. Try specifying the exchange or check the ticker.")
            except Exception:
                st.warning("Yahoo Finance rate limit hit — wait a few seconds and try again.")

    af = {
        "ticker":  st.session_state.get("af_ticker", ""),
        "name":    st.session_state.get("af_name", ""),
        "sector":  st.session_state.get("af_sector", SECTORS[0]),
        "geo":     st.session_state.get("af_geo", GEOS[0]),
        "price":   st.session_state.get("af_price", 0.01),
    }

    st.markdown(
        "<p style='font-size:0.78rem; color:#888; margin-bottom:4px;'>"
        "<span style='color:#00D09C; font-weight:700;'>■</span> Required &nbsp;·&nbsp;"
        "Company info is auto-kept on add-to-existing</p>",
        unsafe_allow_html=True,
    )
    with st.form("add_form", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            ticker  = st.text_input("★ Ticker", value=af["ticker"]).strip().upper()
            name    = st.text_input("Company Name  (kept if exists)", value=af["name"])
        with c2:
            weight  = st.number_input("★ Weight (%)", min_value=0.1, max_value=50.0,
                                      step=0.5, value=float(max(0.1, min(9.5, remaining))))
            entry_p = st.number_input("★ Entry Price", min_value=0.01, step=0.01,
                                      value=float(max(0.01, af["price"])))
            entry_d = st.date_input("★ Entry Date", value=date.today())
        with c3:
            sec_idx = SECTORS.index(af["sector"]) if af["sector"] in SECTORS else 0
            geo_idx = GEOS.index(af["geo"]) if af["geo"] in GEOS else 0
            sector    = st.selectbox("Sector  (kept if exists)",    SECTORS, index=sec_idx)
            geography = st.selectbox("Geography  (kept if exists)", GEOS,    index=geo_idx)
            thematic  = st.selectbox("Thematic  (kept if exists)",  THEMATICS)
        thesis = st.text_area("Thesis  (overwrites only if filled)", height=80)

        new_total = existing_w + weight
        if new_total > 100.5:
            st.warning(f"Total would reach {new_total:.1f}% — exceeds 100%.")

        if st.form_submit_button("Add Position", type="primary"):
            if not ticker or not name or entry_p <= 0:
                st.error("Ticker, Name and Entry Price are required.")
            else:
                add_position({
                    "ticker": ticker, "name": name, "isin": None,
                    "weight": weight, "entry_price": entry_p,
                    "entry_date": str(entry_d), "sector": sector,
                    "geography": geography, "thematic": thematic,
                    "thesis_short": thesis, "is_active": True,
                })
                st.success(f"✓ {ticker} added.")
                for k in ["af_ticker", "af_name", "af_sector", "af_geo", "af_price"]:
                    st.session_state.pop(k, None)
                st.cache_data.clear()
                st.rerun()

# ── CLOSE ─────────────────────────────────────────────────────────────────────
with tab_close:
    if not positions:
        st.info("No active positions.")
    else:
        with st.form("close_form", clear_on_submit=True):
            selected_label = st.selectbox("Position to close", list(pos_options.keys()))
            selected_pos   = pos_options[selected_label]

            st.caption(
                f"Entry: **{selected_pos['entry_price']}** · "
                f"Date: **{selected_pos['entry_date']}** · "
                f"Weight: **{selected_pos['weight']}%**"
            )

            c1, c2, c3 = st.columns(3)
            with c1:
                weight_sold = st.number_input(
                    "Weight to sell (%)",
                    min_value=0.1,
                    max_value=float(selected_pos["weight"]),
                    value=float(selected_pos["weight"]),
                    step=0.5,
                    help="Equal to full weight = full close. Less = partial trim.",
                )
            with c2:
                exit_p = st.number_input("Exit Price", min_value=0.01, step=0.01)
            with c3:
                exit_d = st.date_input("Exit Date", value=date.today())
            reason = st.text_area("Reason", height=80)

            is_full_close = weight_sold >= selected_pos["weight"]
            btn_label = "Confirm Close" if is_full_close else f"Confirm Trim (−{weight_sold}%)"

            if st.form_submit_button(btn_label, type="primary"):
                if exit_p <= 0:
                    st.error("Enter a valid exit price.")
                else:
                    perf = round((exit_p - selected_pos["entry_price"]) / selected_pos["entry_price"] * 100, 2)
                    sign = "+" if perf >= 0 else ""
                    if is_full_close:
                        close_position(selected_pos["id"], exit_p, str(exit_d), reason)
                        st.success(f"✓ {selected_pos['ticker']} closed at {exit_p} ({sign}{perf}%)")
                    else:
                        trim_position(selected_pos["id"], weight_sold, exit_p, str(exit_d), reason)
                        remaining = round(selected_pos["weight"] - weight_sold, 1)
                        st.success(f"✓ {selected_pos['ticker']} trimmed by {weight_sold}% at {exit_p} ({sign}{perf}%) — {remaining}% remaining")
                    st.cache_data.clear()
                    st.rerun()

# ── SWITCH ────────────────────────────────────────────────────────────────────
with tab_switch:
    st.caption("Sell one position and immediately buy another. The new position inherits the same weight.")
    if not positions:
        st.info("No active positions.")
    else:
        with st.form("switch_form", clear_on_submit=True):
            out_label = st.selectbox("Exit this position", list(pos_options.keys()))
            out_pos   = pos_options[out_label]
            st.caption(
                f"Entry: **{out_pos['entry_price']}** · "
                f"Weight: **{out_pos['weight']}%** → will be inherited by new position"
            )

            st.markdown("---")
            c1, c2, c3 = st.columns(3)
            with c1:
                out_p     = st.number_input("Exit Price (OUT)", min_value=0.01, step=0.01)
                in_ticker = st.text_input("New Ticker (IN)").strip().upper()
                in_name   = st.text_input("New Company Name")
            with c2:
                in_p    = st.number_input("Entry Price (IN)", min_value=0.01, step=0.01)
                sw_date = st.date_input("Switch Date", value=date.today())
            with c3:
                in_sector   = st.selectbox("Sector",    SECTORS)
                in_geo      = st.selectbox("Geography", GEOS)
                in_thematic = st.selectbox("Thematic",  THEMATICS)
            in_thesis  = st.text_area("New Thesis", height=80)
            sw_reason  = st.text_area("Reason for switch", height=60)

            if st.form_submit_button("Confirm Switch", type="primary"):
                if not in_ticker or not in_name or out_p <= 0 or in_p <= 0:
                    st.error("All fields are required.")
                else:
                    switch_position(
                        out_id=out_pos["id"], out_price=out_p,
                        in_data={
                            "ticker": in_ticker, "name": in_name, "isin": None,
                            "weight": out_pos["weight"], "entry_price": in_p,
                            "entry_date": str(sw_date), "sector": in_sector,
                            "geography": in_geo, "thematic": in_thematic,
                            "thesis_short": in_thesis, "is_active": True,
                        },
                        date=str(sw_date), reason=sw_reason,
                    )
                    st.success(f"✓ {out_pos['ticker']} → {in_ticker} switched.")
                    st.cache_data.clear()
                    st.rerun()

# ── HISTORY ───────────────────────────────────────────────────────────────────
with tab_history:
    txns = get_transactions()
    if txns:
        df_txn = pd.DataFrame(txns)
        st.dataframe(df_txn[[c for c in [
            "date", "action", "ticker_out", "entry_price_out", "price_out",
            "perf_pct", "ticker_in", "price_in", "reason"
        ] if c in df_txn.columns]], use_container_width=True, hide_index=True)
    else:
        st.info("No transactions yet.")
