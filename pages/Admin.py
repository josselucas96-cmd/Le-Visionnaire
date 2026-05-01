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
    get_setting, upsert_setting, reset_portfolio,
    get_events, add_event, delete_event,
    get_portfolios,
)
from utils.market import get_prices
from utils.research import get_research, upsert_research, delete_research, upload_pdf

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
    c1, c2, c3 = st.columns(3)
    with c1:
        inc = st.text_input("Inception Date (YYYY-MM-DD)",
                            value=get_setting("inception_date", "2026-04-01"))
    with c2:
        name = st.text_input("Portfolio Name",
                             value=get_setting("portfolio_name", "Le Visionnaire"))
    with c3:
        capital = st.number_input("Initial Capital (USD)",
                                  min_value=10_000, max_value=100_000_000,
                                  step=10_000,
                                  value=int(get_setting("initial_capital", "1000000")))
    if st.button("Save Settings"):
        upsert_setting("inception_date", inc)
        upsert_setting("portfolio_name", name)
        upsert_setting("initial_capital", str(capital))
        st.success("Saved.")
        st.cache_data.clear()

    st.markdown("---")
    st.markdown("**Reinitialize Portfolio**")
    st.caption("Resets all entry prices to today's market prices, sets inception date to today, and removes STRC. Transactions history is preserved.")
    if "confirm_reset" not in st.session_state:
        st.session_state.confirm_reset = False
    if not st.session_state.confirm_reset:
        if st.button("Reinitialize Portfolio", type="secondary"):
            st.session_state.confirm_reset = True
            st.rerun()
    else:
        st.warning("Are you sure? This cannot be undone.")
        col_yes, col_no = st.columns(2)
        with col_yes:
            if st.button("Yes, reset", type="primary"):
                _pos = get_positions()
                _tickers = tuple(p["ticker"] for p in _pos if p["ticker"] != "STRC")
                from utils.market import get_prices as _gp
                _raw = _gp(_tickers)
                _prices = {t: _raw[t]["price"] for t in _tickers if _raw.get(t) and _raw[t].get("price")}
                reset_portfolio(date.today().isoformat(), _prices)
                st.cache_data.clear()
                st.session_state.confirm_reset = False
                st.success("Portfolio reinitialized.")
                st.rerun()
        with col_no:
            if st.button("Cancel"):
                st.session_state.confirm_reset = False
                st.rerun()

st.divider()

# ── Performance snapshot ──────────────────────────────────────────────────────
with st.expander("Performance", expanded=False):
    import plotly.graph_objects as go
    from utils.market import get_history, get_prices as _get_prices
    from utils.metrics import (build_portfolio_index, daily_returns, sharpe_ratio,
                               max_drawdown, beta_vs_spy, annualized_volatility, monthly_returns_table)
    from utils.theme import PORTFOLIO_LINE, BENCHMARK_LINE, HLINE_COLOR, BG, TEXT_MID, POSITIVE, NEGATIVE, TRIM
    _positions_perf = get_positions()
    if _positions_perf:
        _inception = get_setting("inception_date", "2026-04-01")
        _tickers_perf = tuple(p["ticker"] for p in _positions_perf)
        _prices_perf = _get_prices(_tickers_perf)
        for p in _positions_perf:
            live = _prices_perf.get(p["ticker"], {})
            p["current_price"] = live.get("price")
            p["change_today"]  = live.get("change_pct")
            if p["current_price"] and p["entry_price"]:
                p["perf_pct"] = round((p["current_price"] - p["entry_price"]) / p["entry_price"] * 100, 2)
            else:
                p["perf_pct"] = None
        _valid = [p for p in _positions_perf if p["perf_pct"] is not None]
        _total_w = sum(p["weight"] for p in _valid) or 1
        _port_perf = sum(p["weight"] * p["perf_pct"] / _total_w for p in _valid)
        _history = get_history(_tickers_perf + ("SPY", "QQQ"), _inception)
        _spy_perf = None
        _spy_index = None
        _qqq_index = None
        if not _history.empty:
            _port_index = build_portfolio_index(_history, _positions_perf)
            if "SPY" in _history.columns:
                _spy_raw = _history["SPY"].dropna()
                _spy_index = _spy_raw / _spy_raw.iloc[0] * 100
                _spy_perf = round(_spy_index.iloc[-1] - 100, 2)
            if "QQQ" in _history.columns:
                _qqq_raw = _history["QQQ"].dropna()
                _qqq_index = _qqq_raw / _qqq_raw.iloc[0] * 100
            _port_ret = daily_returns(_port_index)
            _spy_ret  = daily_returns(_spy_index) if _spy_index is not None else pd.Series()
            _alpha = round(_port_perf - (_spy_perf or 0), 2)
            _today_valid = [p for p in _positions_perf if p.get("change_today") is not None]
            _today = sum(p["weight"] * p["change_today"] for p in _today_valid) / _total_w if _today_valid else None

            pc1, pc2, pc3, pc4 = st.columns(4)
            with pc1:
                s = "+" if _port_perf >= 0 else ""
                st.metric("Portfolio (inception)", f"{s}{_port_perf:.2f}%")
            with pc2:
                s = "+" if (_spy_perf or 0) >= 0 else ""
                st.metric("S&P 500 (inception)", f"{s}{_spy_perf:.2f}%" if _spy_perf is not None else "—")
            with pc3:
                s = "+" if _alpha >= 0 else ""
                st.metric("Alpha", f"{s}{_alpha:.2f}%")
            with pc4:
                if _today is not None:
                    s = "+" if _today >= 0 else ""
                    st.metric("Today", f"{s}{_today:.2f}%")
                else:
                    st.metric("Today", "—")

            # Chart
            _fig = go.Figure()
            _fig.add_trace(go.Scatter(
                x=_port_index.index, y=_port_index.values, name="Le Visionnaire",
                line=dict(color=PORTFOLIO_LINE, width=3, shape="spline", smoothing=0.8),
                hovertemplate="%{x|%b %d, %Y}<br>Portfolio: %{y:.1f}<extra></extra>",
            ))
            if _spy_index is not None:
                _fig.add_trace(go.Scatter(
                    x=_spy_index.index, y=_spy_index.values, name="S&P 500",
                    line=dict(color=BENCHMARK_LINE, width=1.5, dash="dot", shape="spline", smoothing=0.6),
                    hovertemplate="%{x|%b %d, %Y}<br>S&P 500: %{y:.1f}<extra></extra>",
                ))
            if _qqq_index is not None:
                _fig.add_trace(go.Scatter(
                    x=_qqq_index.index, y=_qqq_index.values, name="Nasdaq 100",
                    visible="legendonly",
                    line=dict(color="#A78BFA", width=1.5, dash="dash", shape="spline", smoothing=0.6),
                    hovertemplate="%{x|%b %d, %Y}<br>Nasdaq 100: %{y:.1f}<extra></extra>",
                ))
            _fig.add_hline(y=100, line_dash="dash", line_color=HLINE_COLOR, line_width=1)
            _fig.update_layout(
                plot_bgcolor=BG, paper_bgcolor=BG,
                font=dict(color=TEXT_MID, size=11),
                height=340, hovermode="x unified",
                yaxis=dict(title="Base 100", gridcolor="#161D2E", zeroline=False),
                xaxis=dict(gridcolor="#161D2E"),
                margin=dict(l=0, r=0, t=20, b=0),
                legend=dict(orientation="h", yanchor="top", y=-0.1, xanchor="center", x=0.5,
                            font=dict(size=10), bgcolor="rgba(0,0,0,0)"),
            )
            st.plotly_chart(_fig, use_container_width=True)

            sr1, sr2, sr3 = st.columns(3)
            with sr1:
                s = sharpe_ratio(_port_ret)
                st.metric("Sharpe (ann.)", f"{s:.2f}" if s is not None else "—")
            with sr2:
                md = max_drawdown(_port_index)
                st.metric("Max Drawdown", f"{md:.2f}%" if md is not None else "—")
            with sr3:
                b = beta_vs_spy(_port_ret, _spy_ret)
                st.metric("Beta vs S&P 500", f"{b:.2f}" if b is not None else "—")

            # Monthly returns
            st.write("")
            st.markdown("**Monthly Returns (%)**")
            _mrt = monthly_returns_table(_port_index)
            if not _mrt.empty:
                def _color_m(col):
                    return ["color: #00D09C" if pd.notna(v) and v > 0
                            else "color: #FF4B4B" if pd.notna(v) and v < 0
                            else "" for v in col]
                _fmt = {m: lambda v: f"{v:+.1f}" if pd.notna(v) else "" for m in _mrt.columns}
                st.dataframe(_mrt.style.format(_fmt).apply(_color_m),
                             use_container_width=True, height=38 + min(len(_mrt), 10) * 35)
    else:
        st.info("No positions to compute performance.")

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

    # Dynamic weights + NAV
    initial_capital = float(get_setting("initial_capital", "1000000"))
    initial_cash = max(0.0, 100.0 - total_weight)
    for p in positions:
        if p.get("current_price") and p.get("entry_price"):
            p["current_value"] = p["weight"] * (p["current_price"] / p["entry_price"])
        else:
            p["current_value"] = p["weight"]
    total_current_value = sum(p["current_value"] for p in positions) + initial_cash
    for p in positions:
        p["current_weight"] = round(p["current_value"] / total_current_value * 100, 2)
        p["nav_usd"] = round(p["current_weight"] / 100 * initial_capital * (total_current_value / 100), 0)
    current_cash_pct = round(initial_cash / total_current_value * 100, 1)
    nav_total = round(initial_capital * total_current_value / 100, 0)

    st.caption(
        f"Alloc. deployed: **{total_weight:.1f}%** · "
        f"Initial cash: **{initial_cash:.1f}%** · "
        f"Current cash: **{current_cash_pct:.1f}%** · "
        f"NAV: **${nav_total:,.0f}**"
    )

    # Rebuild df AFTER dynamic weights have been added to position dicts
    df_pos2 = pd.DataFrame(positions)
    display_cols = [c for c in [
        "ticker", "name", "weight", "current_weight", "nav_usd", "entry_price", "current_price",
        "perf_pct", "change_today", "entry_date",
        "sector", "geography", "thematic", "thesis_short"
    ] if c in df_pos2.columns]

    display_admin = df_pos2[display_cols].rename(columns={
        "ticker":         "Ticker",
        "name":           "Name",
        "weight":         "Alloc.",
        "current_weight": "Current %",
        "nav_usd":        "NAV (USD)",
        "entry_price":    "Entry",
        "current_price":  "Price",
        "perf_pct":       "Perf %",
        "change_today":   "Today %",
        "entry_date":     "Entry Date",
        "sector":         "Sector",
        "geography":      "Geography",
        "thematic":       "Thematic",
        "thesis_short":   "Thesis",
    })

    def color_signed_admin(col):
        return [
            "color: #00D09C" if isinstance(v, (int, float)) and v > 0
            else "color: #FF4B4B" if isinstance(v, (int, float)) and v < 0
            else "" for v in col
        ]

    styled = display_admin.style.format({
        "Alloc.":    lambda v: f"{v:.1f}%" if isinstance(v, (int, float)) else "",
        "Current %": lambda v: f"{v:.2f}%" if isinstance(v, (int, float)) else "",
        "NAV (USD)": lambda v: f"${v:,.0f}" if isinstance(v, (int, float)) else "",
        "Entry":     lambda v: f"{v:.2f}" if isinstance(v, (int, float)) else "",
        "Price":     lambda v: f"{v:.2f}" if isinstance(v, (int, float)) else "",
        "Perf %":    lambda v: f"{v:+.2f}%" if isinstance(v, (int, float)) else "",
        "Today %":   lambda v: f"{v:+.2f}%" if isinstance(v, (int, float)) else "",
    }).apply(color_signed_admin, subset=["Perf %", "Today %"])

    table_height = 38 + min(len(positions), 20) * 35
    st.dataframe(styled, use_container_width=True, hide_index=True, height=table_height)

    cash_color = "#00D09C" if 2 < current_cash_pct < 8 else "#FFA500" if current_cash_pct <= 10 else "#FF4B4B"
    st.markdown(
        f"<span style='color:{cash_color}; font-weight:600;'>"
        f"CASH — Initial: {initial_cash:.1f}% · Current: {current_cash_pct:.1f}%</span>",
        unsafe_allow_html=True,
    )
else:
    st.info("No active positions.")

st.divider()

# ── Earnings & Events Calendar ────────────────────────────────────────────────
@st.cache_data(ttl=3600)
def fetch_upcoming_earnings_v3(tickers: tuple) -> tuple:
    """Pull next earnings date + EPS + Revenue estimate per ticker. Cached 1h.
    .calendar gives EPS Avg + Revenue Avg; .earnings_dates is a fallback for date/EPS.
    """
    today = pd.Timestamp.today().normalize()
    horizon = today + pd.Timedelta(days=180)
    events = []
    errors = {}

    for t in tickers:
        event_date = None
        eps_est = None
        rev_est = None
        err_msg = None

        # 1) Primary: .calendar — has both EPS Avg and Revenue Avg
        try:
            cal = yf.Ticker(t).calendar
            if isinstance(cal, dict) and "Earnings Date" in cal:
                dates = cal["Earnings Date"]
                if dates:
                    for d in dates:
                        d_ts = pd.Timestamp(d).normalize()
                        if d_ts >= today:
                            event_date = d_ts
                            if cal.get("Earnings Average") is not None:
                                eps_est = float(cal["Earnings Average"])
                            if cal.get("Revenue Average") is not None:
                                rev_est = float(cal["Revenue Average"])
                            break
        except Exception as e:
            err_msg = f"calendar: {type(e).__name__}: {str(e)[:60]}"

        # 2) Fallback for date (revenue stays None): .earnings_dates
        if event_date is None:
            try:
                ed_df = yf.Ticker(t).earnings_dates
                if ed_df is not None and not ed_df.empty:
                    idx = ed_df.index
                    if hasattr(idx, "tz") and idx.tz is not None:
                        idx = idx.tz_localize(None)
                    idx_norm = pd.DatetimeIndex(idx).normalize()
                    mask = idx_norm >= today
                    if mask.any():
                        event_date = pd.Timestamp(idx_norm[mask][0])
                        if "EPS Estimate" in ed_df.columns:
                            eps_val = ed_df["EPS Estimate"].iloc[int(mask.argmax())]
                            if pd.notna(eps_val):
                                eps_est = float(eps_val)
            except Exception as e:
                if err_msg is None:
                    err_msg = f"earnings_dates: {type(e).__name__}: {str(e)[:60]}"

        if event_date is not None and today <= event_date <= horizon:
            events.append({
                "Ticker":   t,
                "Type":     "Earnings",
                "Date":     event_date.strftime("%Y-%m-%d"),
                "Days":     int((event_date - today).days),
                "EPS Est.": eps_est,
                "Rev Est.": rev_est,
            })
        elif err_msg:
            errors[t] = err_msg

    return events, errors


def _fmt_revenue(v):
    """Format revenue in $X.XB / $XXXM."""
    if v is None or not isinstance(v, (int, float)) or pd.isna(v):
        return "—"
    if abs(v) >= 1e9:
        return f"${v / 1e9:.2f}B"
    if abs(v) >= 1e6:
        return f"${v / 1e6:.0f}M"
    return f"${v:,.0f}"


EVENT_TYPES = ["Earnings", "Investor Day", "Product Launch", "FDA / Regulatory",
               "Conference", "FOMC / Macro", "Index Rebalance", "Other"]

with st.expander("📅 Earnings & Events Calendar", expanded=False):
    cap_col, btn_col = st.columns([5, 1])
    with cap_col:
        st.caption("Auto-pulled earnings + your custom events. Plan ahead for catalysts.")
    with btn_col:
        if st.button("↻ Refresh", key="refresh_earnings", help="Bypass cache and re-fetch"):
            fetch_upcoming_earnings_v3.clear()
            st.rerun()

    if not positions:
        st.info("No active positions.")
    else:
        with st.spinner("Loading earnings calendar…"):
            auto_events, fetch_errors = fetch_upcoming_earnings_v3(tuple(p["ticker"] for p in positions))

        # Custom events (from Supabase)
        try:
            custom_raw = get_events()
        except Exception:
            custom_raw = []
            st.warning("Custom events unavailable — has the `events` table been created in Supabase?")

        today_ts = pd.Timestamp.today().normalize()
        custom_events = []
        for e in custom_raw:
            try:
                d_ts = pd.Timestamp(e["event_date"])
                if d_ts >= today_ts:
                    custom_events.append({
                        "id":       e["id"],
                        "Ticker":   e.get("ticker") or "—",
                        "Type":     e["event_type"],
                        "Title":    e.get("title") or "",
                        "Date":     d_ts.strftime("%Y-%m-%d"),
                        "Days":     (d_ts - today_ts).days,
                        "EPS Est.": None,
                        "Rev Est.": None,
                    })
            except Exception:
                continue

        for e in auto_events:
            e["Title"] = "Earnings release"

        all_events = sorted(auto_events + custom_events, key=lambda x: x["Days"])

        # Tickers we couldn't find earnings for
        found_tickers = {e["Ticker"] for e in auto_events}
        missing = [p["ticker"] for p in positions if p["ticker"] not in found_tickers]

        if not all_events:
            st.info("No upcoming events.")
        else:
            df_all = pd.DataFrame(all_events)[["Date", "Days", "Ticker", "Type", "Title", "EPS Est.", "Rev Est."]]

            def _color_urgency(row):
                d = row["Days"]
                if d <= 7:
                    return ["background-color: rgba(255, 75, 75, 0.15); font-weight: 600"] * len(row)
                if d <= 30:
                    return ["background-color: rgba(255, 165, 0, 0.10)"] * len(row)
                return [""] * len(row)

            styled_e = df_all.style.apply(_color_urgency, axis=1).format({
                "Days":     lambda v: f"{int(v)}d" if pd.notna(v) else "—",
                "EPS Est.": lambda v: f"${v:.2f}" if pd.notna(v) else "—",
                "Rev Est.": _fmt_revenue,
            })
            h_e = 38 + min(len(all_events), 25) * 35
            st.dataframe(styled_e, use_container_width=True, hide_index=True, height=h_e)

            within_7  = sum(1 for e in all_events if e["Days"] <= 7)
            within_30 = sum(1 for e in all_events if e["Days"] <= 30)
            st.caption(
                f"📅 {len(all_events)} upcoming · "
                f"🔴 {within_7} within 7 days · "
                f"🟠 {within_30 - within_7} within 8–30 days"
            )

        if missing:
            st.caption(f"_No auto earnings data for: {', '.join(missing)}_")

        if fetch_errors:
            with st.expander("⚠ Fetch errors (debug)", expanded=False):
                for tk, err in fetch_errors.items():
                    st.text(f"{tk}: {err}")

        # ── Add custom event ──
        st.markdown("---")
        st.markdown("**➕ Add a custom event**")
        with st.form("event_add_form", clear_on_submit=True):
            ec1, ec2, ec3 = st.columns([1, 1.5, 1.5])
            with ec1:
                ev_ticker = st.text_input("Ticker (optional)", placeholder="TSLA").strip().upper()
            with ec2:
                ev_type = st.selectbox("Event Type", EVENT_TYPES, index=1)
            with ec3:
                ev_date = st.date_input("Event Date", value=date.today())
            ev_title = st.text_input("Title *", placeholder="e.g. Tesla Investor Day 2026")
            ev_notes = st.text_area("Notes (optional)", height=60)

            if st.form_submit_button("Add Event", type="primary"):
                if not ev_title:
                    st.error("Title is required.")
                else:
                    try:
                        add_event({
                            "ticker":     ev_ticker or None,
                            "event_type": ev_type,
                            "event_date": str(ev_date),
                            "title":      ev_title,
                            "notes":      ev_notes or None,
                        })
                        st.success(f"✓ {ev_title} added.")
                        st.cache_data.clear()
                        st.rerun()
                    except Exception as e:
                        st.error(f"Could not save: {e}")

        # ── Manage existing custom events ──
        if custom_events:
            st.markdown("**🗂 Manage custom events**")
            for ce in custom_events:
                mc1, mc2, mc3, mc4 = st.columns([1, 1.5, 5, 0.5])
                with mc1: st.markdown(f"`{ce['Ticker']}`")
                with mc2: st.markdown(f"_{ce['Date']}_ · {ce['Type']}")
                with mc3: st.markdown(ce["Title"])
                with mc4:
                    if st.button("🗑", key=f"del_evt_{ce['id']}", help="Delete"):
                        delete_event(ce["id"])
                        st.cache_data.clear()
                        st.rerun()

st.divider()

LAYERS     = ["Core", "Conviction", "Moonshot", "Cash/Equivalent"]
SECTORS    = ["Tech", "Healthcare", "Consumer", "Finance", "Communication",
              "Industrials", "Energy", "Materials", "Real Estate", "Utilities"]
GEOS       = ["USA", "Europe", "Japan", "Asia ex-Japan", "Emerging Markets", "LatAm", "Global", "Other"]
THEMATICS  = ["AI / Semi", "Crypto Currencies Play", "Biotech", "Digital Health",
              "Space / Defense", "Robotics / Automation", "Social Platform",
              "Fintech / Payments", "Consumer Growth", "Energy Transition",
              "Software / SaaS", "Cybersecurity", "Cloud / Infrastructure", "Other"]

pos_options = {f"{p['ticker']}  —  {p['name']}": p for p in positions}

tab_add, tab_close, tab_switch, tab_history, tab_research = st.tabs([
    "➕  Add", "✖  Close", "🔄  Switch", "📋  History", "📄  Documents"
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
    lk1, lk2, lk3, lk4 = st.columns([2, 2, 1.5, 1])
    with lk1:
        lookup_ticker = st.text_input("Ticker", key="lookup_ticker",
                                      placeholder="e.g. TSLA, MC, ENI").strip().upper()
    with lk2:
        exchange_label = st.selectbox("Exchange (optional)", list(EXCHANGES.keys()), key="lookup_exchange")
    with lk3:
        lookup_date = st.date_input("★ Entry Date", value=date.today(), key="lookup_date")
    with lk4:
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
                    st.session_state["af_ticker"] = resolved
                    st.session_state["af_name"]   = info.get("longName") or info.get("shortName") or ""
                    st.session_state["af_sector"] = SECTOR_MAP.get(info.get("sector", ""), "")
                    st.session_state["af_geo"]    = GEO_MAP.get(info.get("country", ""), "Other")
                    # Try historical close for the selected date; fall back to live price
                    try:
                        from datetime import timedelta
                        hist = yf.Ticker(resolved).history(
                            start=lookup_date,
                            end=lookup_date + timedelta(days=4),
                        )
                        hist_price = float(hist["Close"].iloc[0]) if not hist.empty else None
                    except Exception:
                        hist_price = None
                    if hist_price:
                        st.session_state["af_price"] = round(hist_price, 2)
                    else:
                        live = info.get("currentPrice") or info.get("regularMarketPrice") or 0.0
                        st.session_state["af_price"] = float(live)
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
            entry_d = st.date_input("Entry Date", value=lookup_date)
        with c3:
            sec_idx = SECTORS.index(af["sector"]) if af["sector"] in SECTORS else 0
            geo_idx = GEOS.index(af["geo"]) if af["geo"] in GEOS else 0
            layer     = st.selectbox("★ Layer",                       LAYERS)
            sector    = st.selectbox("Sector  (kept if exists)",    SECTORS, index=sec_idx)
            geography = st.selectbox("Geography  (kept if exists)", GEOS,    index=geo_idx)
            thematic  = st.selectbox("Thematic  (kept if exists)",  THEMATICS)
        thesis = st.text_area("Thesis  (overwrites only if filled)", height=80)

        new_total = existing_w + weight
        over_limit = new_total > 100.0
        if over_limit:
            st.error(f"Total would reach {new_total:.1f}% — no leverage allowed. Reduce weight.")

        if st.form_submit_button("Add Position", type="primary"):
            if not ticker or not name or entry_p <= 0:
                st.error("Ticker, Name and Entry Price are required.")
            elif over_limit:
                st.error(f"Cannot add: total weight {new_total:.1f}% exceeds 100%.")
            else:
                add_position({
                    "ticker": ticker, "name": name, "isin": None,
                    "layer": layer,
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
        # Selectbox outside form so max_value updates dynamically
        selected_label = st.selectbox("Position to close", list(pos_options.keys()), key="close_select")
        selected_pos   = pos_options[selected_label]

        live_price = selected_pos.get("current_price") or 0.01
        st.caption(
            f"Entry: **{selected_pos['entry_price']}** · "
            f"Date: **{selected_pos['entry_date']}** · "
            f"Weight: **{selected_pos['weight']}%**"
        )

        with st.form("close_form", clear_on_submit=True):
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
                exit_p = st.number_input("Exit Price", min_value=0.01, step=0.01,
                                         value=float(max(0.01, live_price)))
            with c3:
                exit_d = st.date_input("Exit Date", value=date.today())
            reason = st.text_area("Reason", height=80)

            is_full_close = weight_sold >= selected_pos["weight"]
            btn_label = "Confirm Close" if is_full_close else f"Confirm Trim (−{weight_sold}%)"

            if st.form_submit_button(btn_label, type="primary"):
                if exit_p <= 0:
                    st.error("Enter a valid exit price.")
                elif weight_sold > selected_pos["weight"]:
                    st.error(f"Cannot sell {weight_sold}% — position is only {selected_pos['weight']}%.")
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
    st.caption("Sell one position and immediately buy another.")
    if not positions:
        st.info("No active positions.")
    else:
        # OUT position selector (outside form so caption updates)
        sw_out_label = st.selectbox("Exit this position", list(pos_options.keys()), key="sw_out_label")
        sw_out_pos   = pos_options[sw_out_label]
        st.caption(
            f"Entry: **{sw_out_pos['entry_price']}** · "
            f"Weight: **{sw_out_pos['weight']}%**"
        )

        st.markdown("---")

        # Lookup for the IN position (outside form)
        sw1, sw2, sw3, sw4 = st.columns([2, 2, 1.5, 1])
        with sw1:
            sw_lookup_ticker = st.text_input("New Ticker (IN)", key="sw_lookup_ticker",
                                             placeholder="e.g. MSTR, MC, ENI").strip().upper()
        with sw2:
            sw_exchange_label = st.selectbox("Exchange (optional)", list(EXCHANGES.keys()), key="sw_lookup_exchange")
        with sw3:
            sw_lookup_date = st.date_input("★ Switch Date", value=date.today(), key="sw_lookup_date")
        with sw4:
            st.write("")
            st.write("")
            sw_do_lookup = st.button("Lookup", type="secondary", key="sw_lookup_btn")

        if sw_do_lookup:
            if sw_lookup_ticker:
                suffix = EXCHANGES[sw_exchange_label]
                try:
                    with st.spinner(f"Fetching {sw_lookup_ticker}…"):
                        resolved, info = resolve_ticker(sw_lookup_ticker, suffix)
                    if _valid_info(info):
                        st.session_state["sw_ticker"]  = resolved
                        st.session_state["sw_name"]    = info.get("longName") or info.get("shortName") or ""
                        st.session_state["sw_sector"]  = SECTOR_MAP.get(info.get("sector", ""), "")
                        st.session_state["sw_geo"]     = GEO_MAP.get(info.get("country", ""), "Other")
                        try:
                            from datetime import timedelta
                            hist = yf.Ticker(resolved).history(
                                start=sw_lookup_date,
                                end=sw_lookup_date + timedelta(days=4),
                            )
                            hist_price = float(hist["Close"].iloc[0]) if not hist.empty else None
                        except Exception:
                            hist_price = None
                        if hist_price:
                            st.session_state["sw_price"] = round(hist_price, 2)
                        else:
                            live = info.get("currentPrice") or info.get("regularMarketPrice") or 0.0
                            st.session_state["sw_price"] = float(live)
                        if resolved != sw_lookup_ticker:
                            st.info(f"Resolved as **{resolved}** — {st.session_state['sw_name']}")
                    else:
                        st.warning(f"'{sw_lookup_ticker}' not found. Try specifying the exchange.")
                except Exception:
                    st.warning("Yahoo Finance rate limit hit — wait a few seconds and try again.")

        sw_af = {
            "ticker":  st.session_state.get("sw_ticker", ""),
            "name":    st.session_state.get("sw_name", ""),
            "sector":  st.session_state.get("sw_sector", SECTORS[0]),
            "geo":     st.session_state.get("sw_geo", GEOS[0]),
            "price":   st.session_state.get("sw_price", 0.01),
        }

        with st.form("switch_form", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            with c1:
                out_p     = st.number_input("★ Exit Price (OUT)", min_value=0.01, step=0.01)
                in_ticker = st.text_input("★ Ticker (IN)", value=sw_af["ticker"]).strip().upper()
                in_name   = st.text_input("Company Name", value=sw_af["name"])
            with c2:
                in_weight = st.number_input(
                    "★ Weight IN (%)",
                    min_value=0.1, max_value=float(sw_out_pos["weight"]),
                    value=float(sw_out_pos["weight"]), step=0.5,
                    help="Defaults to full OUT weight. Can be less (leaves cash).",
                )
                in_p    = st.number_input("★ Entry Price (IN)", min_value=0.01, step=0.01,
                                          value=float(max(0.01, sw_af["price"])))
            with c3:
                sw_sec_idx = SECTORS.index(sw_af["sector"]) if sw_af["sector"] in SECTORS else 0
                sw_geo_idx = GEOS.index(sw_af["geo"]) if sw_af["geo"] in GEOS else 0
                in_layer    = st.selectbox("★ Layer",    LAYERS)
                in_sector   = st.selectbox("Sector",    SECTORS, index=sw_sec_idx)
                in_geo      = st.selectbox("Geography", GEOS,    index=sw_geo_idx)
                in_thematic = st.selectbox("Thematic",  THEMATICS)
            in_thesis  = st.text_area("New Thesis", height=80)
            sw_reason  = st.text_area("Reason for switch", height=60)

            if st.form_submit_button("Confirm Switch", type="primary"):
                if not in_ticker or not in_name or out_p <= 0 or in_p <= 0:
                    st.error("All ★ fields are required.")
                else:
                    switch_position(
                        out_id=sw_out_pos["id"], out_price=out_p,
                        in_data={
                            "ticker": in_ticker, "name": in_name, "isin": None,
                            "layer": in_layer,
                            "weight": in_weight, "entry_price": in_p,
                            "entry_date": str(sw_lookup_date), "sector": in_sector,
                            "geography": in_geo, "thematic": in_thematic,
                            "thesis_short": in_thesis, "is_active": True,
                        },
                        date=str(sw_lookup_date), reason=sw_reason,
                    )
                    st.success(f"✓ {sw_out_pos['ticker']} → {in_ticker} switched.")
                    for k in ["sw_ticker", "sw_name", "sw_sector", "sw_geo", "sw_price"]:
                        st.session_state.pop(k, None)
                    st.cache_data.clear()
                    st.rerun()

# ── HISTORY ───────────────────────────────────────────────────────────────────
with tab_history:
    txns = get_transactions()
    if txns:
        df_txn = pd.DataFrame(txns)
        cols = [c for c in [
            "date", "action",
            "ticker_out", "weight_out", "entry_price_out", "price_out", "perf_pct",
            "ticker_in",  "weight_in",  "price_in",
            "reason"
        ] if c in df_txn.columns]
        df_display = df_txn[cols].rename(columns={
            "ticker_out":       "Out",
            "weight_out":       "W.Out %",
            "entry_price_out":  "Entry",
            "price_out":        "Exit Price",
            "perf_pct":         "Perf %",
            "ticker_in":        "In",
            "weight_in":        "W.In %",
            "price_in":         "In Price",
        })
        def color_perf(col):
            return [
                "color: #00D09C" if isinstance(v, (int, float)) and v > 0
                else "color: #FF4B4B" if isinstance(v, (int, float)) and v < 0
                else "" for v in col
            ]
        fmt = {}
        if "Perf %" in df_display.columns:
            fmt["Perf %"] = lambda v: f"{v:+.2f}%" if isinstance(v, (int, float)) else "—"
        if "W.Out %" in df_display.columns:
            fmt["W.Out %"] = lambda v: f"{v:.1f}%" if isinstance(v, (int, float)) else "—"
        if "W.In %" in df_display.columns:
            fmt["W.In %"] = lambda v: f"{v:.1f}%" if isinstance(v, (int, float)) else "—"
        styled_txn = df_display.style.format(fmt)
        if "Perf %" in df_display.columns:
            styled_txn = styled_txn.apply(color_perf, subset=["Perf %"])
        h = 38 + min(len(df_display), 20) * 35
        st.dataframe(styled_txn, use_container_width=True, hide_index=True, height=h)
    else:
        st.info("No transactions yet.")

# ── DOCUMENTS ─────────────────────────────────────────────────────────────────
# Build doc-type options dynamically: Stock Paper + one entry per portfolio.
# When a new portfolio is inserted in the portfolios table, it appears here automatically.
_portfolios_for_docs = get_portfolios()
DOC_TYPE_OPTIONS = ["Stock Paper"] + [f"{p['name']} Document" for p in _portfolios_for_docs]


def _resolve_doc_type(label: str):
    """Map a UI label to (doc_type, portfolio_id) for storage."""
    if label == "Stock Paper":
        return ("Stock Paper", None)
    for p in _portfolios_for_docs:
        if label == f"{p['name']} Document":
            return ("Portfolio Document", p["id"])
    return ("Stock Paper", None)


def _label_for_doc(doc: dict) -> str:
    """Reverse: derive a human label from a stored doc dict."""
    if doc.get("doc_type") == "Stock Paper":
        return "Stock Paper"
    pid = doc.get("portfolio_id")
    for p in _portfolios_for_docs:
        if p["id"] == pid:
            return f"{p['name']} Document"
    return doc.get("doc_type") or "—"


with tab_research:
    st.subheader("Documents")

    # ── Upload new document ──
    st.markdown("#### New Document")
    r_file = st.file_uploader(
        "Drop your PDF here or click to browse",
        type=["pdf"],
        help="PDF only. Max 200MB.",
    )
    with st.form("research_form", clear_on_submit=True):
        r1, r2, r3_col = st.columns([2, 1, 1])
        with r1:
            r_title = st.text_input("★ Title")
        with r2:
            r_doc_type_label = st.selectbox("Document Type", DOC_TYPE_OPTIONS)
        with r3_col:
            r_ticker = st.text_input("Ticker (optional)").strip().upper()
        r_summary = st.text_area("Summary (shown on the public page)", height=80)
        r3, r4 = st.columns(2)
        with r3:
            r_date = st.date_input("Publication Date", value=date.today())
        with r4:
            r_status = st.selectbox("Status", ["hidden", "published", "locked"])

        if st.form_submit_button("Upload & Save", type="primary"):
            if not r_title:
                st.error("Title is required.")
            elif not r_file:
                st.error("Please drop or select a PDF file above.")
            else:
                with st.spinner("Uploading…"):
                    import re, unicodedata
                    slug = re.sub(r"[^a-z0-9]+", "-", unicodedata.normalize("NFKD", r_title).encode("ascii", "ignore").decode().lower()).strip("-")
                    filename = f"{r_date}_{slug}.pdf"
                    url = upload_pdf(r_file.read(), filename)
                doc_type, doc_pid = _resolve_doc_type(r_doc_type_label)
                upsert_research({
                    "title": r_title,
                    "ticker": r_ticker or None,
                    "summary": r_summary,
                    "file_url": url,
                    "status": r_status,
                    "published_at": str(r_date),
                    "doc_type": doc_type,
                    "portfolio_id": doc_pid,
                })
                st.success(f"✓ '{r_title}' saved as {r_status} ({r_doc_type_label}).")
                st.rerun()

    st.divider()

    # ── Existing documents — fetch all statuses, bypass cache ──
    from utils.data import get_client as _get_client
    papers = _get_client().table("research").select("*").order("published_at", desc=True).execute().data
    if not papers:
        st.info("No papers yet.")
    else:
        STATUS_COLORS = {"published": "#00D09C", "locked": "#FFA500", "hidden": "#666"}
        for p in papers:
            col_info, col_type, col_status, col_del = st.columns([5, 1.5, 1.5, 0.5])
            with col_info:
                ticker_tag = f"**{p['ticker']}** — " if p.get("ticker") else ""
                st.markdown(f"{ticker_tag}{p['title']}  \n"
                            f"<span style='font-size:0.78rem; color:#666;'>{p.get('published_at','')}</span>",
                            unsafe_allow_html=True)
            with col_type:
                st.markdown(
                    f"<span style='font-size:0.75rem; color:#888;'>{_label_for_doc(p)}</span>",
                    unsafe_allow_html=True
                )
            with col_status:
                new_status = st.selectbox(
                    "Status", ["published", "locked", "hidden"],
                    index=["published", "locked", "hidden"].index(p["status"]),
                    key=f"status_{p['id']}",
                    label_visibility="collapsed",
                )
                if new_status != p["status"]:
                    upsert_research({"id": p["id"], "status": new_status})
                    st.cache_data.clear()
                    st.rerun()
            with col_del:
                if st.button("🗑", key=f"del_{p['id']}", help="Delete"):
                    delete_research(p["id"])
                    st.cache_data.clear()
                    st.rerun()
