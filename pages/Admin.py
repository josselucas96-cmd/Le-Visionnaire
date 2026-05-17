"""
Admin Cockpit — password protected.
Only you should access this page. It lets you add/close positions and manage settings.
"""
import streamlit as st
from utils import SPECULA_ICON
import pandas as pd
import yfinance as yf
from datetime import date

from utils.data import (
    get_positions, get_transactions,
    add_position, close_position, trim_position,
    get_setting, upsert_setting, reset_portfolio,
    get_events, add_event, delete_event,
    get_portfolios, get_portfolio, update_portfolio,
    get_cash_amount,
)
from utils.market import (
    get_prices_from_db as get_prices,   # display path: read from Supabase (fast, EOD)
    get_prices as get_prices_live,      # move execution path: yfinance live (needed at commit time)
    get_fx_to_usd,
    get_valuation_fundamentals_from_db as get_valuation_fundamentals,  # phase 3 cutover 2026-05-17
    get_bitcoin_price, BTC_HOLDINGS_NAKAMOTO,
)
from utils.nav_history import get_nav_series, get_nav_from_holdings
from utils.research import get_research, upsert_research, delete_research, upload_pdf

st.set_page_config(page_title="Cockpit | Admin", page_icon=SPECULA_ICON, layout="wide")

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
# active_only=False so the Admin sees ALL portfolios including hidden ones
# (e.g., the sandbox `test` portfolio used for infra testing without touching live).
_portfolios_admin = get_portfolios(active_only=False)
if not _portfolios_admin:
    st.error("No portfolios configured in the `portfolios` table.")
    st.stop()
_pf_ids   = [p["id"]   for p in _portfolios_admin]
_pf_names = [p["name"] for p in _portfolios_admin]
if "admin_pf_id" not in st.session_state or st.session_state.admin_pf_id not in _pf_ids:
    st.session_state.admin_pf_id = _pf_ids[0]

# Title row + Logout
col_title, col_logout = st.columns([8, 1])
with col_title:
    st.title("Cockpit")
with col_logout:
    st.write("")
    st.write("")
    if st.button("Logout"):
        st.session_state.authenticated = False
        st.rerun()

# Portfolio selector — three cards in a row.
# Click a card to switch the selected portfolio; everything below
# (Active Positions, Health Tracker, Earnings, Add/Close/Switch tabs)
# operates on the selected one.
_PF_VIS = {
    "visionnaire": ("Le Visionnaire", "High-Conviction Equity",        "#6366F1"),
    "batisseur":   ("Le Bâtisseur",   "Quality Compounders + Tactical", "#F5B60A"),
    "nakamoto":    ("Le Nakamoto",    "Bitcoin Treasury Equities",      "#FF6A00"),
    "test":        ("Portfolio_Test", "Sandbox — infra testing only",   "#22C55E"),
}

st.markdown("""
<style>
.adm-pf-card {
    background: #0D1117;
    border: 1px solid #1F2937;
    border-radius: 12px;
    padding: 1.2rem 1.4rem 0.6rem 1.4rem;
    text-align: left;
    transition: border-color 0.15s, transform 0.15s;
    margin-bottom: 0.4rem;
}
.adm-pf-card-active {
    border-width: 2px;
    padding: 1.15rem 1.35rem 0.55rem 1.35rem;  /* compensate 1px extra border */
}
.adm-pf-eyebrow {
    font-size: 0.62rem;
    font-weight: 700;
    letter-spacing: 2px;
    text-transform: uppercase;
    margin-bottom: 0.4rem;
}
.adm-pf-name {
    font-family: 'Cormorant Garamond', Georgia, serif !important;
    font-size: 1.5rem;
    font-weight: 700;
    color: #F9FAFB;
    margin-bottom: 0.25rem;
    line-height: 1.1;
}
.adm-pf-sub {
    font-size: 0.75rem;
    color: #6B7280;
    letter-spacing: 0.3px;
}
</style>
""", unsafe_allow_html=True)

_card_cols = st.columns(len(_pf_ids))
for _col, _pid_iter in zip(_card_cols, _pf_ids):
    _name, _sub, _color = _PF_VIS.get(
        _pid_iter,
        (next((p["name"] for p in _portfolios_admin if p["id"] == _pid_iter), _pid_iter),
         "", "#6B7280"),
    )
    _is_active = (_pid_iter == st.session_state.admin_pf_id)
    _border = _color if _is_active else "#1F2937"
    _eyebrow_color = _color
    with _col:
        st.markdown(
            f'<div class="adm-pf-card{" adm-pf-card-active" if _is_active else ""}" '
            f'style="border-color:{_border};">'
            f'<div class="adm-pf-eyebrow" style="color:{_eyebrow_color};">'
            f'Portfolio · {_pid_iter.upper()}</div>'
            f'<div class="adm-pf-name">{_name}</div>'
            f'<div class="adm-pf-sub">{_sub}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        _btn_lbl = "Selected ▼" if _is_active else "Select"
        if st.button(_btn_lbl, key=f"adm_pf_btn_{_pid_iter}",
                     use_container_width=True,
                     type="primary" if _is_active else "secondary"):
            st.session_state.admin_pf_id = _pid_iter
            st.rerun()

_pid = st.session_state.admin_pf_id
_pf  = get_portfolio(_pid) or {}

# Per-portfolio capital key with backward-compat fallback for Visionnaire.
# (Settings UI removed; helper kept because Active Positions reads initial_capital.)
def _capital_key(pid):
    return f"initial_capital_{pid}"

def _read_initial_capital(pid):
    val = get_setting(_capital_key(pid))
    if val is None and pid == "visionnaire":
        val = get_setting("initial_capital")
    return float(val) if val else 1_000_000.0

st.divider()

# ── NAV model comparison (Phase C dual-read, Admin-only) ─────────────────────
with st.expander("🔬 NAV Model Comparison (legacy vs new)", expanded=False):
    st.caption(
        "Dual-read panel for validating the new real-$ fund accounting model "
        "(daily_holdings) against the legacy cost-basis chart formula "
        "(build_portfolio_index → nav_history). Public pages still use legacy "
        "until Phase D cutover."
    )
    _rows_compare = []
    for _pid_cmp in ("visionnaire", "batisseur", "nakamoto"):
        _old = get_nav_series(_pid_cmp)
        _new = get_nav_from_holdings(_pid_cmp)
        _old_perf = float(_old.iloc[-1] - 100) if not _old.empty else None
        _new_perf = float(_new.iloc[-1] - 100) if not _new.empty else None
        _rows_compare.append({
            "Portfolio":    _pid_cmp,
            "Old (legacy)": f"{_old_perf:+.2f}%" if _old_perf is not None else "—",
            "New (real-$)": f"{_new_perf:+.2f}%" if _new_perf is not None else "—",
            "Δ (pp)":       f"{(_new_perf - _old_perf):+.2f}" if (_old_perf is not None and _new_perf is not None) else "—",
            "Rows in DB":   len(_new),
        })
    st.dataframe(pd.DataFrame(_rows_compare), use_container_width=True, hide_index=True)
    st.caption(
        "Δ explains: new model is NAV-neutral on rebalances (no PRU averaging "
        "artifacts) and uses yfinance close at T-1 as a clean base. Larger Δ "
        "on Bâtisseur/Nakamoto reflects the PRU-vs-close gap at inception day."
    )

st.divider()

# ── Performance snapshot (uses the same render fn as the public pages) ────────
with st.expander("Performance", expanded=False):
    from utils.portfolio import render_performance_chart_section
    from utils.market import get_history, get_prices_from_db as _get_prices
    from utils.theme import PORTFOLIO_LINE

    _positions_perf = get_positions(portfolio_id=_pid)
    if not _positions_perf:
        st.info("No positions to compute performance.")
    else:
        _inception = str(_pf.get("inception_date", "2026-04-01"))
        _bench_pri = _pf.get("benchmark_primary")
        _bench_pri_lbl = _pf.get("benchmark_primary_label") or _bench_pri or ""
        _bench_sec = _pf.get("benchmark_secondary")
        _bench_sec_lbl = _pf.get("benchmark_secondary_label") or _bench_sec or ""
        _accent = _pf.get("color_primary") or PORTFOLIO_LINE
        _portfolio_name = _pf.get("name", _pid)
        _tickers_perf = tuple(p["ticker"] for p in _positions_perf)

        # Fetch live (cached) prices to compute "Today" weighted average
        _prices_perf = _get_prices(_tickers_perf)
        for p in _positions_perf:
            live = _prices_perf.get(p["ticker"], {})
            p["change_today"] = live.get("change_pct")

        # Fetch benchmark series from T-1 anchor (same convention as public)
        def _prev_trading_day(d_str):
            c = pd.Timestamp(d_str) - pd.Timedelta(days=1)
            while c.weekday() >= 5:
                c -= pd.Timedelta(days=1)
            return c.date().isoformat()
        _chart_start = _prev_trading_day(_inception)
        _bench_tickers = tuple(b for b in (_bench_pri, _bench_sec) if b)
        _history = get_history(_tickers_perf + _bench_tickers, _chart_start)

        _primary_index = None
        _primary_perf = None
        _secondary_index = None
        if not _history.empty:
            if _bench_pri and _bench_pri in _history.columns:
                _raw = _history[_bench_pri].dropna()
                if not _raw.empty:
                    _primary_index = _raw / _raw.iloc[0] * 100
                    _primary_perf = round(_primary_index.iloc[-1] - 100, 2)
            if _bench_sec and _bench_sec in _history.columns:
                _raw = _history[_bench_sec].dropna()
                if not _raw.empty:
                    _secondary_index = _raw / _raw.iloc[0] * 100

        _port_index = get_nav_from_holdings(_pid)
        # Trim port_index to benchmark end date (same as public)
        _bench_ends = []
        if _primary_index is not None and not _primary_index.empty:
            _bench_ends.append(_primary_index.index[-1])
        if _secondary_index is not None and not _secondary_index.empty:
            _bench_ends.append(_secondary_index.index[-1])
        if _bench_ends and _port_index is not None and not _port_index.empty:
            _port_index = _port_index[_port_index.index <= min(_bench_ends)]

        # Metrics row (4 cols) — Admin-specific layout, kept inline since
        # the public page renders these outside the expander differently.
        _port_perf = round(float(_port_index.iloc[-1] - 100), 2) if (_port_index is not None and not _port_index.empty) else 0.0
        _alpha = round(_port_perf - (_primary_perf or 0), 2)
        _today_valid = [p for p in _positions_perf if p.get("change_today") is not None]
        _total_w = sum(p["weight"] for p in _today_valid) or 1
        _today = sum(p["weight"] * p["change_today"] for p in _today_valid) / _total_w if _today_valid else None

        pc1, pc2, pc3, pc4 = st.columns(4)
        with pc1:
            s = "+" if _port_perf >= 0 else ""
            st.metric("Portfolio (inception)", f"{s}{_port_perf:.2f}%")
        with pc2:
            s = "+" if (_primary_perf or 0) >= 0 else ""
            st.metric(f"{_bench_pri_lbl} (inception)" if _bench_pri_lbl else "Benchmark (inception)",
                      f"{s}{_primary_perf:.2f}%" if _primary_perf is not None else "—")
        with pc3:
            s = "+" if _alpha >= 0 else ""
            st.metric("Alpha", f"{s}{_alpha:.2f}%")
        with pc4:
            if _today is not None:
                s = "+" if _today >= 0 else ""
                st.metric("Today", f"{s}{_today:.2f}%")
            else:
                st.metric("Today", "—")

        # Chart + Sharpe/MD/Beta + Monthly Returns — shared with public pages
        render_performance_chart_section(
            portfolio_name=_portfolio_name,
            accent_color=_accent,
            inception_date=_inception,
            bench_pri_lbl=_bench_pri_lbl,
            bench_sec_lbl=_bench_sec_lbl,
            port_index=_port_index,
            primary_index=_primary_index,
            secondary_index=_secondary_index,
        )

st.divider()

# ── Active positions ──────────────────────────────────────────────────────────
positions = get_positions(portfolio_id=_pid)
st.subheader(f"Active Positions — {_pf.get('name', _pid)} ({len(positions)})")

if positions:
    tickers_live = tuple(p["ticker"] for p in positions)
    prices_live  = get_prices(tickers_live)

    # Fetch FX rates for non-USD market caps so we can display in USD.
    _ccys_needed = tuple({(prices_live.get(t, {}) or {}).get("currency") or "USD"
                          for t in tickers_live})
    _fx_rates = get_fx_to_usd(_ccys_needed)

    for p in positions:
        live = prices_live.get(p["ticker"], {})
        p["current_price"] = live.get("price")
        p["change_today"]  = live.get("change_pct")
        _mc_local = live.get("market_cap")
        _ccy      = live.get("currency") or "USD"
        _rate     = _fx_rates.get(_ccy)
        p["market_cap_usd"] = (_mc_local * _rate) if (_mc_local and _rate) else None
        if p["current_price"] and p["entry_price"]:
            p["perf_pct"] = round(
                (p["current_price"] - p["entry_price"]) / p["entry_price"] * 100, 2
            )
        else:
            p["perf_pct"] = None

    # Portfolio-specific valuation ratio:
    #   Visionnaire → P/S (market_cap / revenue_ttm)
    #   Bâtisseur   → Fwd PE (from yfinance)
    #   Nakamoto    → EV/mNAV (enterprise_value_usd / (BTC_held × BTC_price))
    _funds_admin = get_valuation_fundamentals(tickers_live)
    _ratio_label = None
    if _pid == "visionnaire":
        _ratio_label = "P/S"
        for p in positions:
            f = _funds_admin.get(p["ticker"], {}) or {}
            mc, rev = f.get("market_cap"), f.get("revenue_ttm")
            p["valo_ratio"] = round(mc / rev, 2) if (mc and rev and rev > 0) else None
    elif _pid == "batisseur":
        _ratio_label = "Fwd PE"
        for p in positions:
            f = _funds_admin.get(p["ticker"], {}) or {}
            fpe = f.get("forward_pe")
            p["valo_ratio"] = round(float(fpe), 2) if fpe else None
    elif _pid == "nakamoto":
        _ratio_label = "EV/mNAV"
        btc_price = get_bitcoin_price()
        for p in positions:
            f = _funds_admin.get(p["ticker"], {}) or {}
            ev = f.get("enterprise_value")
            ccy = (prices_live.get(p["ticker"]) or {}).get("currency") or "USD"
            rate = _fx_rates.get(ccy) or 1.0
            ev_usd = ev * rate if ev else None
            btc_held = BTC_HOLDINGS_NAKAMOTO.get(p["ticker"], 0)
            nav_usd = btc_held * btc_price if (btc_held and btc_price) else None
            p["valo_ratio"] = round(ev_usd / nav_usd, 2) if (ev_usd and nav_usd and nav_usd > 0) else None

    df_pos = pd.DataFrame(positions)
    total_weight = df_pos["weight"].sum()

    # Fund-accounting allocation (real $): position $-value = shares × current_price;
    # cash $ derived from daily_holdings via get_cash_amount (portfolios.cash_amount
    # is RLS-blocked, see data.py docstring). current_weight = position$ / NAV × 100.
    initial_capital = _read_initial_capital(_pid)
    cash_amount = get_cash_amount(_pid)
    for p in positions:
        cp = p.get("current_price")
        shares = float(p.get("shares") or 0)
        if cp and shares > 0:
            p["current_value_usd"] = shares * float(cp)
        elif cp and p.get("entry_price"):
            cost = float(p.get("weight") or 0) * initial_capital / 100.0
            p["current_value_usd"] = cost * (float(cp) / float(p["entry_price"]))
        else:
            p["current_value_usd"] = float(p.get("weight") or 0) * initial_capital / 100.0
    nav_total_usd = sum(p["current_value_usd"] for p in positions) + cash_amount
    if nav_total_usd <= 0:
        nav_total_usd = initial_capital
    for p in positions:
        p["current_weight"] = round(p["current_value_usd"] / nav_total_usd * 100, 2)
        p["nav_usd"] = round(p["current_value_usd"], 0)
        # `current_value` (in % of initial_capital units) is what
        # _pru_compute_rebalance uses for T_untouched. Without this set,
        # the formula falls back to stored cost-basis weight and the
        # target-drifted math is off (user types 6%, gets ~6.5% in
        # current % because T_after is inflated by ~9pp on this portfolio).
        p["current_value"] = p["current_value_usd"] / initial_capital * 100.0
    current_cash_pct = round(cash_amount / nav_total_usd * 100, 1)
    nav_total = round(nav_total_usd, 0)
    # `initial_cash` is the cost-basis cash% at inception (= 100 - Σ weights). Kept
    # for the "CASH — Initial" label below; differs from current_cash_pct once trims
    # have realized gains beyond cost basis.
    initial_cash = max(0.0, 100.0 - total_weight)

    st.caption(
        f"Alloc. deployed: **{total_weight:.1f}%** · "
        f"Initial cash: **{initial_cash:.1f}%** · "
        f"Current cash: **{current_cash_pct:.1f}%** · "
        f"NAV: **${nav_total:,.0f}**"
    )

    # Rebuild df AFTER dynamic weights have been added to position dicts
    df_pos2 = pd.DataFrame(positions)
    display_cols = [c for c in [
        "ticker", "name", "weight", "current_weight", "nav_usd",
        "market_cap_usd", "valo_ratio",
        "entry_price", "current_price",
        "perf_pct", "change_today", "entry_date",
        "sector", "geography", "thematic", "thesis_short"
    ] if c in df_pos2.columns]

    _rename_map = {
        "ticker":         "Ticker",
        "name":           "Name",
        "weight":         "Alloc.",
        "current_weight": "Current %",
        "nav_usd":        "NAV (USD)",
        "market_cap_usd": "Market Cap (USD)",
        "valo_ratio":     _ratio_label or "Valo",
        "entry_price":    "PRU",
        "current_price":  "Price",
        "perf_pct":       "Perf %",
        "change_today":   "Today %",
        "entry_date":     "Entry Date",
        "sector":         "Sector",
        "geography":      "Geography",
        "thematic":       "Thematic",
        "thesis_short":   "Thesis",
    }
    display_admin = df_pos2[display_cols].rename(columns=_rename_map)

    def color_signed_admin(col):
        return [
            "color: #00D09C" if isinstance(v, (int, float)) and v > 0
            else "color: #FF4B4B" if isinstance(v, (int, float)) and v < 0
            else "" for v in col
        ]

    def _format_mcap(v):
        """Dynamic T/B/M formatter for market cap so we can fit the
        full equity universe (large-cap $T → micro-cap $M) in one column."""
        if not isinstance(v, (int, float)) or pd.isna(v):
            return "—"
        abs_v = abs(v)
        if abs_v >= 1e12: return f"${v / 1e12:.2f}T"
        if abs_v >= 1e9:  return f"${v / 1e9:.1f}B"
        if abs_v >= 1e6:  return f"${v / 1e6:.0f}M"
        return f"${v:,.0f}"

    _fmt = {
        "Alloc.":            lambda v: f"{v:.1f}%" if isinstance(v, (int, float)) else "",
        "Current %":         lambda v: f"{v:.2f}%" if isinstance(v, (int, float)) else "",
        "NAV (USD)":         lambda v: f"${v:,.0f}" if isinstance(v, (int, float)) else "",
        "Market Cap (USD)":  _format_mcap,
        "PRU":               lambda v: f"{v:.2f}" if isinstance(v, (int, float)) else "",
        "Price":             lambda v: f"{v:.2f}" if isinstance(v, (int, float)) else "",
        "Perf %":            lambda v: f"{v:+.2f}%" if isinstance(v, (int, float)) else "",
        "Today %":           lambda v: f"{v:+.2f}%" if isinstance(v, (int, float)) else "",
    }
    if _ratio_label:
        _fmt[_ratio_label] = lambda v: f"{v:.2f}" if isinstance(v, (int, float)) and pd.notna(v) else "—"
    styled = display_admin.style.format(_fmt).apply(color_signed_admin, subset=["Perf %", "Today %"])

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

# ── Valo Tracking ─────────────────────────────────────────────────────────────
with st.expander(f"📐 Valo Tracking — {_pf.get('name', _pid)}", expanded=False):
    if not positions:
        st.info("No positions to evaluate.")
    else:
        from utils.market import get_valuation_fundamentals_from_db as get_valuation_fundamentals
        from utils.data   import update_position_valuation

        cap_col, refresh_col = st.columns([5, 1])
        with cap_col:
            st.caption(
                "Forward valuation tracking. Edit **RG / GM / OM** (your 2-3y "
                "expected averages, in %), then **Save**. All growth-adjusted "
                "ratios use your RG; EV/GM and PSG-Q use your GM and OM."
            )
        with refresh_col:
            if st.button("↻ Refresh fundamentals", key="valo_refresh",
                         help="Bypass yfinance cache (1h)"):
                get_valuation_fundamentals.clear()
                st.rerun()

        _v_tickers = tuple(p["ticker"] for p in positions)
        with st.spinner("Loading fundamentals…"):
            _funds = get_valuation_fundamentals(_v_tickers)

        # ─── Per-row reset machinery ────────────────────────────────────
        # Streamlit's data_editor keeps an internal frontend state that
        # isn't reliably synced when we mutate session_state[key] directly.
        # Instead we (1) version the widget key so a reset spawns a fresh
        # widget, and (2) keep our own snapshot of the current values so
        # OTHER rows' edits survive the widget replacement.
        _snapshot_key = f"valo_snapshot_{_pid}"
        _widget_v_key = f"valo_widget_v_{_pid}"
        if _snapshot_key not in st.session_state:
            st.session_state[_snapshot_key] = {}
        if _widget_v_key not in st.session_state:
            st.session_state[_widget_v_key] = 0
        _snapshot = st.session_state[_snapshot_key]
        _reset_pending_key = f"valo_reset_pending_{_pid}"  # set of tickers
        if _reset_pending_key not in st.session_state:
            st.session_state[_reset_pending_key] = set()
        _reset_pending = st.session_state[_reset_pending_key]

        # Build the editable inputs DataFrame.
        _inputs_rows = []
        for p in positions:
            t = p["ticker"]
            f = _funds.get(t, {})
            _gm_ttm  = (f.get("gross_margin")     or 0) * 100  # %
            _om_ttm  = (f.get("operating_margin") or 0) * 100  # %
            _fcf_ttm = (f.get("fcf_margin")       or 0) * 100  # %
            _ana_rg  = f.get("analyst_rg")  # already in %
            _ana_rg_round = round(_ana_rg, 1) if _ana_rg is not None else None

            if t in _reset_pending:
                # Force defaults for tickers being reset on this render
                rg_value  = _ana_rg_round
                gm_value  = round(_gm_ttm, 1)
                om_value  = round(_om_ttm, 1)
                fcf_value = round(_fcf_ttm, 1)
            elif t in _snapshot:
                # Carry over the user's current edits (across the widget bump)
                e = _snapshot[t]
                rg_value  = e.get("RG % (exp)")
                gm_value  = e.get("GM % (exp)")
                om_value  = e.get("OM % (exp)")
                fcf_value = e.get("FCF % (exp)")
            else:
                # Fresh load: use DB override if any, else seeds (analyst/TTM)
                rg_value  = p.get("expected_revenue_growth") if p.get("expected_revenue_growth") is not None else _ana_rg_round
                gm_value  = p.get("expected_gross_margin")   if p.get("expected_gross_margin")   is not None else round(_gm_ttm,  1)
                om_value  = p.get("expected_op_margin")      if p.get("expected_op_margin")      is not None else round(_om_ttm,  1)
                fcf_value = p.get("expected_fcf_margin")     if p.get("expected_fcf_margin")     is not None else round(_fcf_ttm, 1)

            _inputs_rows.append({
                "Ticker":      t,
                "Name":        p.get("name", ""),
                "RG % (exp)":  rg_value,
                "Analyst":     _ana_rg_round,
                "GM % (exp)":  gm_value,
                "OM % (exp)":  om_value,
                "FCF % (exp)": fcf_value,
                "↺":           False,
            })
        _inputs_df = pd.DataFrame(_inputs_rows)

        # Versioned key — bumps on each reset so the widget is reborn fresh.
        _editor_key = f"valo_inputs_{_pid}_v{st.session_state[_widget_v_key]}"
        edited_inputs = st.data_editor(
            _inputs_df,
            key=_editor_key,
            hide_index=True,
            use_container_width=True,
            num_rows="fixed",
            column_config={
                "Ticker":      st.column_config.TextColumn(disabled=True, width="small"),
                "Name":        st.column_config.TextColumn(disabled=True, width="medium"),
                "RG % (exp)":  st.column_config.NumberColumn(
                    "RG %", format="%.1f", min_value=-50.0, max_value=300.0, step=1.0,
                    help="Expected average revenue growth, 2-3 years (in %). Defaults to analyst consensus.",
                ),
                "Analyst":     st.column_config.NumberColumn(
                    "Analyst", format="%.1f", disabled=True,
                    help="Analyst consensus revenue growth (forward +1y from yfinance). Read-only reference.",
                ),
                "GM % (exp)":  st.column_config.NumberColumn(
                    "GM %", format="%.1f", min_value=0.0,   max_value=100.0, step=1.0,
                    help="Expected average gross margin, 2-3 years (in %)",
                ),
                "OM % (exp)":  st.column_config.NumberColumn(
                    "OM %", format="%.1f", min_value=-50.0, max_value=80.0, step=1.0,
                    help="Expected average operating margin, 2-3 years (in %)",
                ),
                "FCF % (exp)": st.column_config.NumberColumn(
                    "FCF %", format="%.1f", min_value=-50.0, max_value=80.0, step=1.0,
                    help="Expected average free cash flow margin, 2-3 years (in %)",
                ),
                "↺":           st.column_config.CheckboxColumn(
                    "↺", default=False, width="small",
                    help="Tick to reset this row to defaults (analyst RG · TTM margins). "
                         "Cell-level only — click Save afterward to persist.",
                ),
            },
        )

        # Capture current edits into our snapshot so they survive the next
        # widget bump (when a reset happens elsewhere on the table).
        for i, p in enumerate(positions):
            t = p["ticker"]
            row = edited_inputs.iloc[i]
            _snapshot[t] = {
                "RG % (exp)":  row["RG % (exp)"],
                "GM % (exp)":  row["GM % (exp)"],
                "OM % (exp)":  row["OM % (exp)"],
                "FCF % (exp)": row["FCF % (exp)"],
            }
        # The reset-pending set has been consumed by the input_df build above.
        _reset_pending.clear()

        # Detect ↺ clicks on this render → schedule reset for next render.
        _needs_reset_rerun = False
        for i, p in enumerate(positions):
            try:
                _ticked = bool(edited_inputs.iloc[i].get("↺", False))
            except Exception:
                _ticked = False
            if not _ticked:
                continue
            t = p["ticker"]
            _reset_pending.add(t)
            # Drop from snapshot so input_df build uses the seeds instead
            if t in _snapshot:
                del _snapshot[t]
            _needs_reset_rerun = True
        if _needs_reset_rerun:
            # Bump the widget version so st.data_editor instantiates a new
            # internal state (no leftover edits from the previous widget).
            st.session_state[_widget_v_key] += 1
            st.rerun()

        # Compute live ratios from edited inputs.
        def _safe_div(a, b):
            try:
                if a is None or b is None or b == 0:
                    return None
                return a / b
            except Exception:
                return None

        _ratio_rows = []
        for i, p in enumerate(positions):
            t = p["ticker"]
            f = _funds.get(t, {})
            mc      = f.get("market_cap")
            ev      = f.get("enterprise_value")
            rev     = f.get("revenue_ttm")
            ebitda  = f.get("ebitda")
            fwd_pe  = f.get("forward_pe")

            row = edited_inputs.iloc[i]
            rg  = row["RG % (exp)"]
            gm  = row["GM % (exp)"]
            om  = row["OM % (exp)"]
            fcf = row["FCF % (exp)"]
            ana = row.get("Analyst")
            d_ana = (rg - ana) if (rg is not None and pd.notna(rg) and ana is not None and pd.notna(ana)) else None

            # Forward GP estimate uses user's GM applied to TTM revenue.
            gp_est = (rev * gm / 100.0) if (rev and gm and gm > 0) else None

            ps        = _safe_div(mc,  rev)
            evs       = _safe_div(ev,  rev)
            evgp      = _safe_div(ev,  gp_est)
            ev_ebitda = _safe_div(ev,  ebitda) if (ebitda and ebitda > 0) else None

            evgprg  = _safe_div(evgp, rg) if (rg and rg > 0) else None
            psgq    = (evs / (rg * om)  * 100) if (evs is not None and rg and om  and rg > 0 and om  > 0) else None
            psgfcf  = (evs / (rg * fcf) * 100) if (evs is not None and rg and fcf and rg > 0 and fcf > 0) else None

            if _pid == "batisseur":
                # Bâtisseur ratios: PE-focused for quality compounders.
                # Forward PE 2Y = Forward PE 1Y / (1 + RG/100)  — assumes constant margins.
                fwd_pe_2y = (fwd_pe / (1 + rg / 100.0)) if (fwd_pe and rg) else None
                _ratio_rows.append({
                    "Ticker":       t,
                    "MCap ($M)":    round(mc / 1e6) if mc  else None,
                    "EV ($M)":      round(ev / 1e6) if ev  else None,
                    "Rev TTM ($M)": round(rev / 1e6) if rev else None,
                    "EBITDA ($M)":  round(ebitda / 1e6) if ebitda else None,
                    "Δ Analyst":    round(d_ana,    1) if d_ana     is not None else None,
                    "P/S":          round(ps,        2) if ps        is not None else None,
                    "EV/EBITDA":    round(ev_ebitda, 2) if ev_ebitda is not None else None,
                    "EV/GM":        round(evgp,      2) if evgp      is not None else None,
                    "Fwd PE 1Y":    round(fwd_pe,    2) if fwd_pe    is not None else None,
                    "Fwd PE 2Y":    round(fwd_pe_2y, 2) if fwd_pe_2y is not None else None,
                    "EV/GM/RG":     round(evgprg,    2) if evgprg    is not None else None,
                    "PSG-Q":        round(psgq,      2) if psgq      is not None else None,
                    "PSG-FCF":      round(psgfcf,    2) if psgfcf    is not None else None,
                })
            else:
                # Visionnaire (and others by default): growth-tilted ratios.
                psg     = _safe_div(ps,   rg) if (rg and rg > 0) else None
                evsg    = _safe_div(evs,  rg) if (rg and rg > 0) else None
                _ratio_rows.append({
                    "Ticker":         t,
                    "MCap ($M)":      round(mc / 1e6) if mc  else None,
                    "EV ($M)":        round(ev / 1e6) if ev  else None,
                    "Rev TTM ($M)":   round(rev / 1e6) if rev else None,
                    "Δ Analyst":      round(d_ana,  1) if d_ana   is not None else None,
                    "P/S":            round(ps,     2) if ps      is not None else None,
                    "EV/S":           round(evs,    2) if evs     is not None else None,
                    "EV/GM":          round(evgp,   2) if evgp    is not None else None,
                    "P/S/RG (PSG)":   round(psg,    2) if psg     is not None else None,
                    "EV/S/RG":        round(evsg,   2) if evsg    is not None else None,
                    "EV/GM/RG":       round(evgprg, 2) if evgprg  is not None else None,
                    "PSG-Q":          round(psgq,   2) if psgq    is not None else None,
                    "PSG-FCF":        round(psgfcf, 2) if psgfcf  is not None else None,
                })
        _ratios_df = pd.DataFrame(_ratio_rows)

        # Color graders — different scales for ratio-style vs PE-style metrics.
        def _color_growth_ratio(v):
            """Lower is better: <1 green; 1–1.5 yellow; 1.5–2 orange; >2 red."""
            if v is None or pd.isna(v): return ""
            if v < 1:   return "color: #10B981; font-weight: 600"
            if v < 1.5: return "color: #FCD34D"
            if v < 2:   return "color: #F97316"
            return "color: #DC2626; font-weight: 600"

        def _color_pe(v):
            """Forward PE: <20 green; 20–30 yellow; 30–40 orange; >40 red."""
            if v is None or pd.isna(v): return ""
            if v < 20: return "color: #10B981; font-weight: 600"
            if v < 30: return "color: #FCD34D"
            if v < 40: return "color: #F97316"
            return "color: #DC2626; font-weight: 600"

        def _color_ev_ebitda(v):
            """EV/EBITDA: <10 green; 10–15 yellow; 15–25 orange; >25 red."""
            if v is None or pd.isna(v): return ""
            if v < 10: return "color: #10B981; font-weight: 600"
            if v < 15: return "color: #FCD34D"
            if v < 25: return "color: #F97316"
            return "color: #DC2626; font-weight: 600"

        def _color_delta(v):
            """Δ vs Analyst RG: positive (you above analyst) = green;
            negative (you below analyst) = red. Magnitude-bold."""
            if v is None or pd.isna(v) or v == 0: return ""
            if v > 0: return "color: #10B981; font-weight: 600"
            return "color: #DC2626; font-weight: 600"

        if _pid == "batisseur":
            _ratio_cols = ["P/S", "EV/EBITDA", "EV/GM", "Fwd PE 1Y", "Fwd PE 2Y",
                           "EV/GM/RG", "PSG-Q", "PSG-FCF"]
            styled = _ratios_df.style.format({
                "MCap ($M)":    "{:,.0f}",
                "EV ($M)":      "{:,.0f}",
                "Rev TTM ($M)": "{:,.0f}",
                "EBITDA ($M)":  "{:,.0f}",
                "Δ Analyst":    "{:+.1f}",
                **{c: "{:.2f}" for c in _ratio_cols},
            }, na_rep="—")
            styled = styled.map(_color_delta,        subset=["Δ Analyst"])
            styled = styled.map(_color_ev_ebitda,    subset=["EV/EBITDA"])
            styled = styled.map(_color_pe,           subset=["Fwd PE 1Y", "Fwd PE 2Y"])
            for c in ["EV/GM/RG", "PSG-Q", "PSG-FCF"]:
                styled = styled.map(_color_growth_ratio, subset=[c])
            _hierarchy = "Fwd PE 1Y → Fwd PE 2Y → EV/EBITDA → EV/GM → EV/GM/RG → PSG-Q → PSG-FCF"
            _legend = (
                "🟢/🟡/🟠/🔴 thresholds — "
                "Fwd PE: <20 / <30 / <40 / >40 · "
                "EV/EBITDA: <10 / <15 / <25 / >25 · "
                "growth-adjusted: <1 / <1.5 / <2 / >2 · "
                "Δ Analyst: 🟢 over / 🔴 under analyst RG"
            )
        else:
            _grad_cols = ["P/S/RG (PSG)", "EV/S/RG", "EV/GM/RG", "PSG-Q", "PSG-FCF"]
            styled = _ratios_df.style.format({
                "MCap ($M)":    "{:,.0f}",
                "EV ($M)":      "{:,.0f}",
                "Rev TTM ($M)": "{:,.0f}",
                "Δ Analyst":    "{:+.1f}",
                **{c: "{:.2f}" for c in ["P/S", "EV/S", "EV/GM"] + _grad_cols},
            }, na_rep="—")
            styled = styled.map(_color_delta, subset=["Δ Analyst"])
            for c in _grad_cols:
                styled = styled.map(_color_growth_ratio, subset=[c])
            _hierarchy = "P/S → EV/S → EV/S/RG → EV/GM/RG → PSG-Q → PSG-FCF"
            _legend = (
                "🟢 <1 · 🟡 1–1.5 · 🟠 1.5–2 · 🔴 >2 · "
                "Δ Analyst: 🟢 over / 🔴 under analyst RG"
            )

        st.markdown("**Computed ratios** (auto-update on each input edit)")
        st.dataframe(styled, use_container_width=True, hide_index=True,
                     height=38 + min(len(positions), 30) * 35)

        st.caption(f"**Hierarchy** : {_hierarchy}   ·   {_legend}")

        # Save button — explicit batched persist.
        if st.button("💾 Save valuation inputs", type="primary", key="valo_save"):
            _failed = []
            with st.spinner("Saving…"):
                for i, p in enumerate(positions):
                    row = edited_inputs.iloc[i]
                    try:
                        update_position_valuation(
                            position_id=p["id"],
                            growth=float(row["RG % (exp)"])  if pd.notna(row["RG % (exp)"])  else None,
                            gm=    float(row["GM % (exp)"])  if pd.notna(row["GM % (exp)"])  else None,
                            om=    float(row["OM % (exp)"])  if pd.notna(row["OM % (exp)"])  else None,
                            fcf=   float(row["FCF % (exp)"]) if pd.notna(row["FCF % (exp)"]) else None,
                        )
                    except Exception as e:
                        _failed.append((p["ticker"], type(e).__name__, str(e)[:300]))
            if _failed:
                st.error(f"❌ {len(_failed)} position(s) failed to save:")
                for tk, etype, emsg in _failed:
                    st.code(f"{tk}  →  {etype}: {emsg}", language=None)
                st.caption(
                    "If you see 'column ... does not exist', run "
                    "`NOTIFY pgrst, 'reload schema';` in Supabase SQL Editor. "
                    "If you see permission errors, check RLS policies on `positions`."
                )
            else:
                # Clear the local snapshot + reset machinery so the next render
                # rebuilds input_df from the freshly saved DB values.
                st.session_state[_snapshot_key] = {}
                st.session_state[_reset_pending_key] = set()
                st.session_state[_widget_v_key] += 1
                st.success(f"Saved {len(positions)} positions.")
                st.cache_data.clear()
                st.rerun()

st.divider()

# ── Portfolio Health Tracker ──────────────────────────────────────────────────
with st.expander(f"🩺 Health Tracker — {_pf.get('name', _pid)}", expanded=True):
    _pos_health = positions  # already loaded above
    if not _pos_health:
        st.info("No positions to evaluate.")
    else:
        from collections import defaultdict

        # UCITS applies on the current NAV-based weight, not the entry weight.
        # current_weight was computed in the Active Positions block above
        # (entry_weight × current_price / entry_price, normalized by total NAV).
        # Fall back to entry weight for positions where market data is missing.
        def _live_w(p):
            cw = p.get("current_weight")
            return float(cw) if cw is not None else float(p["weight"])

        _weights         = [_live_w(p) for p in _pos_health]
        _entry_weights   = [float(p["weight"]) for p in _pos_health]
        _weights_sum     = sum(_weights)
        _weights_sorted  = sorted(_weights, reverse=True)
        _n_pos           = len(_pos_health)
        _top1            = _weights_sorted[0]
        _top3            = sum(_weights_sorted[:3])
        _top5            = sum(_weights_sorted[:5])
        _entry_top1      = max(_entry_weights)
        _cash_pct_h      = float(current_cash_pct)  # already computed in Active Positions block
        _sum_above_5     = sum(w for w in _weights if w > 5.0)
        _n_above_5       = sum(1 for w in _weights if w > 5.0)

        _sector_alloc = defaultdict(float)
        _theme_alloc  = defaultdict(float)
        _geo_alloc    = defaultdict(float)
        for p in _pos_health:
            w = _live_w(p)
            _sector_alloc[p.get("sector")  or "—"] += w
            _theme_alloc [p.get("thematic")or "—"] += w
            _geo_alloc   [p.get("geography")or "—"] += w

        # Status helper — returns (icon, color, label) for a metric vs thresholds
        def _hstat(value, ok_max, watch_max, breach_max):
            if value <= ok_max:
                return ("🟢", "#10B981", "OK")
            if value <= watch_max:
                return ("🟡", "#F59E0B", "Watch")
            if value <= breach_max:
                return ("🟠", "#F97316", "Alert")
            return ("🔴", "#DC2626", "BREACH")

        def _badge(icon, color, label, extra=""):
            return (f"<div style='font-size:0.78rem; color:{color}; font-weight:600; "
                    f"margin-top:-6px;'>{icon} {label}{(' · ' + extra) if extra else ''}</div>")

        # ── UCITS V Compliance (Bâtisseur only) ──────────────────────────────
        if _pid == "batisseur":
            st.markdown("**UCITS V Compliance**")
            u1, u2, u3 = st.columns(3)
            with u1:
                ic, cl, lb = _hstat(_top1, 8.0, 9.5, 10.0)
                st.metric("Max single position", f"{_top1:.2f}%",
                          help="Hard cap 10% · Personal trim alert 9.5%")
                hr = 10.0 - _top1
                st.markdown(_badge(ic, cl, lb, f"headroom {hr:+.1f}pp to cap"),
                            unsafe_allow_html=True)
            with u2:
                ic, cl, lb = _hstat(_sum_above_5, 35.0, 37.0, 40.0)
                st.metric("Sum positions >5%", f"{_sum_above_5:.2f}%",
                          help="Hard cap 40% · Personal alert 37% · Personal trim 39%")
                hr = 40.0 - _sum_above_5
                st.markdown(_badge(ic, cl, lb,
                            f"{_n_above_5} pos >5% · headroom {hr:+.1f}pp"),
                            unsafe_allow_html=True)
            with u3:
                if _n_pos >= 20:
                    ic, cl, lb = "🟢", "#10B981", "OK"
                elif _n_pos >= 16:
                    ic, cl, lb = "🟡", "#F59E0B", "Tight"
                else:
                    ic, cl, lb = "🔴", "#DC2626", "BREACH"
                st.metric("Position count", str(_n_pos), help="UCITS V minimum 16")
                st.markdown(_badge(ic, cl, lb, f"min 16"), unsafe_allow_html=True)
            st.write("")

        # ── Concentration ────────────────────────────────────────────────────
        st.markdown("**Concentration**")
        c1, c2, c3, c4 = st.columns(4)
        with c1: st.metric("Top 1",  f"{_top1:.2f}%")
        with c2: st.metric("Top 3",  f"{_top3:.2f}%")
        with c3: st.metric("Top 5",  f"{_top5:.2f}%")
        with c4: st.metric("Cash",   f"{_cash_pct_h:.2f}%")

        # Concentration flags
        _flags = []
        if _top3 > 35:
            _flags.append(f"Top 3 = {_top3:.1f}% (>35% concentration alert)")
        if _cash_pct_h < 2:
            _flags.append(f"Cash {_cash_pct_h:.1f}% — below operational target")
        elif _cash_pct_h > 15:
            _flags.append(f"Cash {_cash_pct_h:.1f}% — above target, deploy?")
        if _flags:
            for f in _flags:
                st.markdown(f"⚠ {f}")

        st.write("")

        # ── Sector / Thematic / Geography breakdown (3 columns side-by-side) ─
        def _alloc_table(title, alloc_dict, hot_threshold=25.0):
            """Render a sorted alloc table with flags on heavy slices."""
            st.markdown(f"**{title}**")
            df = pd.DataFrame(
                [(k, v) for k, v in sorted(alloc_dict.items(), key=lambda x: -x[1])],
                columns=[title.split()[0], "%"],
            )
            df["%"] = df["%"].round(2)

            def _row_style(row):
                v = row["%"]
                if v >= hot_threshold:
                    return [f"color: #F97316; font-weight: 600"] * len(row)
                if v >= hot_threshold * 0.7:
                    return [f"color: #F59E0B"] * len(row)
                return [""] * len(row)

            styled = df.style.format({"%": "{:.2f}%"}).apply(_row_style, axis=1)
            st.dataframe(styled, use_container_width=True, hide_index=True,
                         height=38 + min(len(df), 12) * 35)

        # Display in 3 columns for compact view, or stacked. 3 cols on wide screens.
        sc, tc, gc = st.columns(3)
        with sc: _alloc_table("Sector",    _sector_alloc, hot_threshold=25.0)
        with tc: _alloc_table("Thematic",  _theme_alloc,  hot_threshold=20.0)
        with gc: _alloc_table("Geography", _geo_alloc,    hot_threshold=70.0)

        st.write("")

        # ── Bâtisseur-specific cluster risks ─────────────────────────────────
        if _pid == "batisseur":
            st.markdown("**Cluster Risks (Bâtisseur-specific)**")

            def _cluster(tickers):
                return sum(float(p["weight"]) for p in _pos_health
                           if p["ticker"] in tickers)

            _ai_capex   = _cluster({"NVDA", "AMZN", "META", "MSFT", "TSM"})
            _healthcare = _cluster({"LLY", "BSX", "ISRG", "NVO", "EL.PA"})
            _luxury     = _cluster({"RACE", "RMS.PA"})
            _em_consumer= _cluster({"MELI", "BABA"})
            _glp1       = _cluster({"LLY", "NVO"})

            cl1, cl2, cl3, cl4, cl5 = st.columns(5)
            with cl1: st.metric("AI capex",       f"{_ai_capex:.1f}%",   help="NVDA+AMZN+META+MSFT (+TSM if held)")
            with cl2: st.metric("Healthcare",     f"{_healthcare:.1f}%", help="LLY+BSX+ISRG+NVO+EL")
            with cl3: st.metric("Luxury",         f"{_luxury:.1f}%",     help="RACE+RMS")
            with cl4: st.metric("EM Consumer",    f"{_em_consumer:.1f}%",help="MELI+BABA")
            with cl5: st.metric("GLP-1 obesity",  f"{_glp1:.1f}%",       help="LLY+NVO (inverse-correlated competitors)")

            _cluster_flags = []
            if _ai_capex > 30:
                _cluster_flags.append(f"AI capex cluster {_ai_capex:.1f}% — watch correlation in AI bear")
            if _healthcare > 20:
                _cluster_flags.append(f"Healthcare cluster {_healthcare:.1f}% — common reimbursement/regulatory exposure")
            if _glp1 > 8:
                _cluster_flags.append(f"GLP-1 cluster {_glp1:.1f}% — narrative-break double impact risk")
            for f in _cluster_flags:
                st.markdown(f"⚠ {f}")

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

tab_moves, tab_history, tab_research = st.tabs([
    "🎯  Moves", "📋  History", "📄  Documents"
])

# ── Ticker lookup helpers (used by Moves tab) ────────────────────────────────
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


def _moves_action_label(current: float, new: float) -> str:
    """Display chip derived from current vs new weight."""
    if abs(new - current) < 0.001:
        return "—"
    if current == 0 and new > 0:
        return "✚ BUY (new)"
    if new == 0 and current > 0:
        return "✗ CLOSE"
    if new > current:
        return "⬆ REINFORCE"
    return "⬇ REDUCE"


def _moves_classify(current: float, new: float) -> str:
    """Internal dispatch tag: BUY / REINFORCE / REDUCE / CLOSE / NOOP."""
    if abs(new - current) < 0.001:
        return "NOOP"
    if current == 0 and new > 0:
        return "BUY"
    if new == 0 and current > 0:
        return "CLOSE"
    if new > current:
        return "REINFORCE"
    return "REDUCE"


def _pru_compute_rebalance(positions_list, draft, prices_live):
    """PRU model + auto-conversion of typed targets to DB weights.

    Returns dict with:
      - moves: list of {ticker, id, action, target_drifted, drift_factor,
                        old_db, new_db, delta_db, current_price, ...}
      - T_after: projected NAV factor post-rebalance
      - initial_cash_after: DB-level cash %
      - cash_drifted_after: drifted cash %
      - projected_drifted: dict ticker → projected drifted % for all positions

    The math closed-form:
        T = 100 × (T_untouched + 100 − sum_untouched_DB) / (100 − X_touched + K)
    where:
        T_untouched = Σ unchanged contributions (= old current_value)
        sum_untouched_DB = Σ unchanged DB weights
        X_touched = Σ target_drifted for touched existing
        K = Σ (target_drifted / drift_factor) for touched existing
        L = Σ target_drifted for new positions
        initial_cash_after = 100 − sum_untouched_DB − T × (K + L) / 100

    Touched/new positions then land at exactly target_drifted (no surprise).
    PRU semantics: entry_price preserved on REDUCE; PRU-averaged on REINFORCE.
    """
    positions_by_id = {p["id"]: p for p in positions_list if p.get("id") is not None}

    T_untouched      = 0.0
    sum_untouched_DB = 0.0
    X_touched        = 0.0
    K                = 0.0
    L                = 0.0
    moves            = []

    for d in draft:
        new_w = float(d["new_weight"])
        if d["id"] is not None:
            orig = positions_by_id.get(d["id"])
            if orig is None:
                continue
            old_db        = float(orig["weight"])
            entry_price   = float(orig["entry_price"])
            current_price = float(orig.get("current_price")
                                  or (prices_live.get(d["ticker"]) or {}).get("price")
                                  or entry_price)
            drift_factor  = (current_price / entry_price) if entry_price > 0 else 1.0

            if new_w == 0:
                moves.append({
                    "ticker": d["ticker"], "id": d["id"],
                    "action": "CLOSE",
                    "target_drifted": 0.0,
                    "drift_factor":   drift_factor,
                    "old_db":         old_db,
                    "current_price":  current_price,
                    "name":           d["name"],
                    "layer":          d.get("layer"),
                    "sector":         d.get("sector"),
                    "geography":      d.get("geography"),
                    "thematic":       d.get("thematic"),
                    "current_weight": d["current_weight"],
                })
                continue

            if abs(new_w - d["current_weight"]) < 0.001:
                # Untouched: drift preserved
                T_untouched      += float(orig.get("current_value") or old_db)
                sum_untouched_DB += old_db
            else:
                # Touched
                X_touched += new_w
                K         += new_w / drift_factor if drift_factor > 0 else new_w
                moves.append({
                    "ticker": d["ticker"], "id": d["id"],
                    "action": None,  # resolved later after delta_db computed
                    "target_drifted": new_w,
                    "drift_factor":   drift_factor,
                    "old_db":         old_db,
                    "current_price":  current_price,
                    "name":           d["name"],
                    "layer":          d.get("layer"),
                    "sector":         d.get("sector"),
                    "geography":      d.get("geography"),
                    "thematic":       d.get("thematic"),
                    "current_weight": d["current_weight"],
                })
        else:
            if new_w > 0:
                L += new_w
                px = (prices_live.get(d["ticker"]) or {}).get("price") or 0.0
                moves.append({
                    "ticker": d["ticker"], "id": None,
                    "action": "BUY",
                    "target_drifted": new_w,
                    "drift_factor":   1.0,
                    "old_db":         0.0,
                    "current_price":  px,
                    "name":           d["name"],
                    "layer":          d.get("layer"),
                    "sector":         d.get("sector"),
                    "geography":      d.get("geography"),
                    "thematic":       d.get("thematic"),
                    "current_weight": 0.0,
                })

    denominator = 100.0 - X_touched + K
    if denominator <= 0:
        return None  # over-allocation / unsolvable

    T_after            = 100.0 * (T_untouched + 100.0 - sum_untouched_DB) / denominator
    initial_cash_after = 100.0 - sum_untouched_DB - T_after * (K + L) / 100.0
    cash_drifted_after = initial_cash_after / T_after * 100.0 if T_after > 0 else 0.0

    # Resolve new_db / delta_db / action for each touched + buy
    for m in moves:
        if m["action"] == "CLOSE":
            m["new_db"]    = 0.0
            m["delta_db"]  = -m["old_db"]
        elif m["action"] == "BUY":
            m["new_db"]    = m["target_drifted"] * T_after / 100.0
            m["delta_db"]  = m["new_db"]
        else:  # touched, action pending
            drift = m["drift_factor"]
            m["new_db"]    = m["target_drifted"] * T_after / (100.0 * drift) if drift > 0 else m["target_drifted"]
            m["delta_db"]  = m["new_db"] - m["old_db"]
            if m["delta_db"] > 0.001:
                m["action"] = "REINFORCE"
            elif m["delta_db"] < -0.001:
                m["action"] = "REDUCE"
            else:
                m["action"] = "NOOP"

    # Build projected_drifted map for all positions
    projected_drifted = {}
    for m in moves:
        if m["action"] == "CLOSE":
            continue
        projected_drifted[m["ticker"]] = m["target_drifted"]
    for p in positions_list:
        if p["ticker"] not in projected_drifted and p.get("id") is not None:
            # Untouched (or not in draft): keep drift
            contrib = float(p.get("current_value") or p["weight"])
            projected_drifted[p["ticker"]] = contrib / T_after * 100.0 if T_after > 0 else 0

    return {
        "moves":              moves,
        "T_after":            T_after,
        "initial_cash_after": initial_cash_after,
        "cash_drifted_after": cash_drifted_after,
        "projected_drifted":  projected_drifted,
    }


with tab_moves:
    st.caption(
        "Edit allocations directly: set **New %** to 0 to close, increase to reinforce, "
        "decrease to reduce. To **add a new position**, fill the empty bottom row — "
        "ticker alone is enough (name / sector / geography auto-fill from yfinance). "
        "Nothing is committed until you click **Preview moves → Confirm**."
    )
    today_str   = str(date.today())
    draft_key   = f"moves_draft_{_pid}"
    ver_key     = f"moves_ver_{_pid}"
    confirm_key = f"moves_confirm_{_pid}"

    if ver_key not in st.session_state:
        st.session_state[ver_key] = 0

    # Seed draft from current positions on first render (or after Reset).
    # "current_weight" displays the drifted (dynamic) allocation, not the entry
    # weight, so the user sees today's reality. "new_weight" defaults to the
    # same value so untouched rows show zero delta = NOOP.
    if draft_key not in st.session_state:
        st.session_state[draft_key] = [
            {
                "id":             p["id"],
                "ticker":         p["ticker"],
                "name":           p["name"],
                "layer":          p.get("layer") or LAYERS[0],
                "sector":         p.get("sector") or SECTORS[0],
                "geography":      p.get("geography") or GEOS[0],
                "thematic":       p.get("thematic") or THEMATICS[0],
                "thesis_short":   p.get("thesis_short") or "",
                "current_weight": float(p.get("current_weight") or p["weight"]),
                "new_weight":     float(p.get("current_weight") or p["weight"]),
                "_is_new":        False,
                "_lookup_done":   True,
            }
            for p in positions
        ]

    # ── Main editor ───────────────────────────────────────────────────────────
    if st.session_state[draft_key]:
        df_draft = (
            pd.DataFrame(st.session_state[draft_key])
              .sort_values(by=["_is_new", "ticker"])
              .reset_index(drop=True)
        )
    else:
        df_draft = pd.DataFrame(columns=[
            "id", "ticker", "name", "layer", "sector", "geography",
            "thematic", "thesis_short", "current_weight", "new_weight",
            "_is_new", "_lookup_done",
        ])

    editor_key = f"moves_editor_{_pid}_v{st.session_state[ver_key]}"
    # Height that fits all rows + 1 add-row + header (no vertical scroll)
    n_rows       = max(len(df_draft), 1)
    table_height = 38 + (n_rows + 1) * 35 + 4

    edited = st.data_editor(
        df_draft,
        column_config={
            "ticker":         st.column_config.TextColumn("Ticker", width="small"),
            "name":           st.column_config.TextColumn("Name"),
            "layer":          st.column_config.SelectboxColumn(
                                  "Layer", options=LAYERS, width="small"),
            "sector":         st.column_config.SelectboxColumn(
                                  "Sector", options=SECTORS, width="small"),
            "geography":      st.column_config.SelectboxColumn(
                                  "Geography", options=GEOS, width="small"),
            "thematic":       st.column_config.SelectboxColumn(
                                  "Thematic", options=THEMATICS, width="medium"),
            "current_weight": st.column_config.NumberColumn(
                                  "Current %", disabled=True, format="%.2f"),
            "new_weight":     st.column_config.NumberColumn(
                                  "New %", min_value=0.0, max_value=100.0,
                                  step=0.5, format="%.2f"),
            "id":             None,
            "thesis_short":   None,
            "_is_new":        None,
            "_lookup_done":   None,
        },
        column_order=["ticker", "name", "layer", "sector", "geography",
                      "thematic", "current_weight", "new_weight"],
        hide_index=True,
        num_rows="dynamic",
        height=table_height,
        key=editor_key,
        use_container_width=True,
    )

    # ── Sync edited rows back to draft (handle adds, edits, deletes, autofill) ──
    existing_by_id  = {d["id"]: d for d in st.session_state[draft_key] if d["id"] is not None}
    edited_records  = edited.to_dict("records")
    edited_ids      = {r["id"] for r in edited_records if pd.notna(r.get("id"))}

    new_draft = []
    df_input_names = {
        d.get("ticker"): d.get("name", "") for d in df_draft.to_dict("records")
    }

    for r in edited_records:
        rid = r.get("id")
        if pd.notna(rid) and rid in existing_by_id:
            # Existing position — keep id/ticker, allow metadata + weight edits
            orig = existing_by_id[rid]
            new_draft.append({
                **orig,
                "name":       (r.get("name") or orig["name"]),
                "layer":      (r.get("layer") or orig["layer"]),
                "sector":     (r.get("sector") or orig["sector"]),
                "geography":  (r.get("geography") or orig["geography"]),
                "thematic":   (r.get("thematic") or orig["thematic"]),
                "new_weight": float(r.get("new_weight") if r.get("new_weight") is not None
                                    else orig["new_weight"]),
            })
        else:
            # New row from the empty bottom add-row
            tkr = str(r.get("ticker") or "").strip().upper()
            if not tkr:
                continue  # skip empty rows
            # Carry over state from prior draft entry with same ticker if it exists
            already = next(
                (d for d in st.session_state[draft_key]
                 if d["id"] is None and d["ticker"] == tkr),
                None,
            )
            base = already or {
                "id":             None,
                "ticker":         tkr,
                "name":           "",
                "layer":          LAYERS[0],
                "sector":         SECTORS[0],
                "geography":      GEOS[0],
                "thematic":       THEMATICS[0],
                "thesis_short":   "",
                "current_weight": 0.0,
                "new_weight":     0.0,
                "_is_new":        True,
                "_lookup_done":   False,
            }
            new_draft.append({
                **base,
                "ticker":     tkr,
                "name":       (r.get("name") or base["name"]),
                "layer":      (r.get("layer") or base["layer"]),
                "sector":     (r.get("sector") or base["sector"]),
                "geography":  (r.get("geography") or base["geography"]),
                "thematic":   (r.get("thematic") or base["thematic"]),
                "new_weight": float(r.get("new_weight") if r.get("new_weight") is not None
                                    else base["new_weight"]),
            })

    # Existing positions deleted from the editor → treat as CLOSE (new_weight = 0)
    for orig in st.session_state[draft_key]:
        if orig["id"] is not None and orig["id"] not in edited_ids:
            new_draft.append({**orig, "new_weight": 0.0})

    # Auto-fill missing name/sector/geo for new rows (one yfinance attempt per ticker)
    autofilled = False
    for d in new_draft:
        if (d.get("_is_new")
                and d.get("ticker")
                and not d.get("name")
                and not d.get("_lookup_done")):
            try:
                with st.spinner(f"Looking up {d['ticker']}…"):
                    resolved, info = resolve_ticker(d["ticker"], None)
                if _valid_info(info):
                    d["ticker"]    = resolved
                    d["name"]      = info.get("longName") or info.get("shortName") or resolved
                    d["sector"]    = SECTOR_MAP.get(info.get("sector", ""), d["sector"]) or d["sector"]
                    d["geography"] = GEO_MAP.get(info.get("country", ""), d["geography"]) or d["geography"]
                    autofilled = True
            except Exception:
                pass
            d["_lookup_done"] = True

    st.session_state[draft_key] = new_draft

    # If autofill changed the data, rerun so the editor shows the filled name/sector/geo
    if autofilled:
        st.session_state[ver_key] += 1
        st.rerun()

    if not st.session_state[draft_key]:
        st.caption("Empty portfolio. Type a ticker in the bottom row of the table to add a position.")

    # ── Compute moves from current draft ──
    moves = []
    for d in st.session_state[draft_key]:
        cls = _moves_classify(d["current_weight"], d["new_weight"])
        if cls == "NOOP":
            continue
        moves.append({
            **d,
            "delta":       d["new_weight"] - d["current_weight"],
            "action":      _moves_action_label(d["current_weight"], d["new_weight"]),
            "action_type": cls,
        })

    # ── Validation ──
    sum_new   = sum(d["new_weight"] for d in st.session_state[draft_key])
    cash_proj = max(0.0, 100.0 - sum_new)
    tickers   = [d["ticker"] for d in st.session_state[draft_key]]
    has_dup   = len(tickers) != len(set(tickers))
    has_neg   = any(d["new_weight"] < 0 for d in st.session_state[draft_key])
    over_100  = sum_new > 100.0 + 0.001
    valid     = not (has_dup or has_neg or over_100)

    vc1, vc2 = st.columns([3, 1])
    with vc1:
        if not valid:
            if over_100:
                st.error(f"❌ Sum of new weights is {sum_new:.2f}% — no leverage allowed.")
            if has_dup:
                st.error("❌ Duplicate tickers in draft.")
            if has_neg:
                st.error("❌ Negative weights not allowed.")
        else:
            st.caption(
                f"Sum of new weights: **{sum_new:.2f}%** · "
                f"Cash projected: **{cash_proj:.2f}%** · ✓ Valid"
            )
    with vc2:
        st.metric("Pending moves", len(moves))

    if moves:
        st.markdown("**Pending changes**")
        preview_df = pd.DataFrame([
            {
                "Action":    m["action"],
                "Ticker":    m["ticker"],
                "Δ %":       m["delta"],
                "Current %": m["current_weight"],
                "New %":     m["new_weight"],
            }
            for m in moves
        ])
        st.dataframe(
            preview_df.style.format({
                "Δ %":       "{:+.2f}",
                "Current %": "{:.2f}",
                "New %":     "{:.2f}",
            }),
            hide_index=True, use_container_width=False,
        )

    # ── Action buttons ──
    bc1, _bcgap, bc3 = st.columns([1, 2, 2])
    with bc1:
        if st.button("Reset edits", key="moves_reset"):
            st.session_state.pop(draft_key, None)
            st.session_state.pop(confirm_key, None)
            st.session_state[ver_key] += 1
            st.rerun()
    with bc3:
        preview_disabled = (not valid) or (not moves)
        if st.button("Preview moves →", type="primary",
                     disabled=preview_disabled, key="moves_preview"):
            st.session_state[confirm_key] = True
            st.rerun()

    # ── Confirmation modal ────────────────────────────────────────────────────
    if st.session_state.get(confirm_key) and moves:
        st.markdown("---")
        with st.container(border=True):
            st.subheader(f"Confirm moves — {_pf.get('name', _pid)} ({len(moves)} transaction(s))")

            move_tickers = tuple(m["ticker"] for m in moves)
            # Moves preview/commit MUST use live yfinance prices (intraday) so
            # the user sees the actual execution price at commit time. Display
            # paths use the EOD cached get_prices, but trading uses live.
            preview_prices = get_prices_live(move_tickers)

            # ── PRU + auto-conversion: project the post-rebalance state ───────
            # Touched/new positions land at exactly their typed target_drifted;
            # entry_price preserved on REDUCE (track record kept), PRU-averaged
            # on REINFORCE (just like add_position already does).
            rebalance = _pru_compute_rebalance(
                positions, st.session_state[draft_key], preview_prices,
            )
            if rebalance is None:
                st.error("Targets unsolvable (over-allocation). Reduce some New % values.")
                st.stop()
            proj_drifted      = rebalance["projected_drifted"]
            proj_cash_drifted = rebalance["cash_drifted_after"]

            # NAV basis for $ estimate
            nav_basis   = globals().get("nav_total") or _read_initial_capital(_pid)
            cash_before = globals().get(
                "current_cash_pct",
                100.0 - sum(d["current_weight"] for d in st.session_state[draft_key]),
            )

            total_cash_flow = 0.0
            rows_html = []
            for m in moves:
                px        = (preview_prices.get(m["ticker"]) or {}).get("price")
                px_str    = f"${px:.2f}" if px else "—"
                usd_amt   = abs(m["delta"]) / 100.0 * nav_basis if nav_basis else 0.0
                cash_sign = -1 if m["delta"] > 0 else 1
                total_cash_flow += cash_sign * usd_amt
                delta_color = "#00D09C" if m["delta"] > 0 else "#FF4B4B"
                after_pct = proj_drifted.get(m["ticker"])
                after_str = f"{after_pct:.2f}%" if after_pct is not None else "—"
                cur_str   = f"{m['current_weight']:.2f}%"
                rows_html.append(
                    f"<tr>"
                    f"<td style='padding:6px 12px'>{m['action']}</td>"
                    f"<td style='padding:6px 12px'><b>{m['ticker']}</b></td>"
                    f"<td style='padding:6px 12px; text-align:right'>{cur_str}</td>"
                    f"<td style='padding:6px 12px; text-align:right; color:{delta_color}'>{m['delta']:+.2f}%</td>"
                    f"<td style='padding:6px 12px; text-align:right; font-weight:600'>{after_str}</td>"
                    f"<td style='padding:6px 12px; text-align:right'>≈ ${usd_amt:,.0f}</td>"
                    f"<td style='padding:6px 12px; text-align:right'>{px_str}</td>"
                    f"</tr>"
                )
            table_html = (
                "<table style='width:100%; border-collapse:collapse; margin-bottom:1rem'>"
                "<thead><tr style='color:#888; border-bottom:1px solid rgba(255,255,255,0.1)'>"
                "<th style='padding:6px 12px; text-align:left'>Action</th>"
                "<th style='padding:6px 12px; text-align:left'>Ticker</th>"
                "<th style='padding:6px 12px; text-align:right'>Current %</th>"
                "<th style='padding:6px 12px; text-align:right'>Δ typed</th>"
                "<th style='padding:6px 12px; text-align:right'>After %</th>"
                "<th style='padding:6px 12px; text-align:right'>USD (est.)</th>"
                "<th style='padding:6px 12px; text-align:right'>Live Price</th>"
                "</tr></thead><tbody>"
                + "".join(rows_html)
                + "</tbody></table>"
            )
            st.markdown(table_html, unsafe_allow_html=True)

            st.caption(
                f"Net cash flow: **${total_cash_flow:+,.0f}** · "
                f"Cash (drifted): **{cash_before:.2f}% → {proj_cash_drifted:.2f}%** · "
                f"Invested: **{(100 - cash_before):.2f}% → {(100 - proj_cash_drifted):.2f}%**"
            )

            # ── Full projected portfolio (all positions, sorted by After %) ──
            with st.expander("📊  Full projected portfolio (after commit)", expanded=False):
                full_rows = []
                draft_by_ticker = {d["ticker"]: d for d in st.session_state[draft_key]}
                # Sort by projected drifted weight descending
                sorted_tickers = sorted(
                    proj_drifted.keys(),
                    key=lambda t: -proj_drifted[t],
                )
                for tkr in sorted_tickers:
                    d = draft_by_ticker.get(tkr)
                    if d is None:
                        continue
                    after_pct   = proj_drifted[tkr]
                    current_pct = d["current_weight"]
                    delta       = after_pct - current_pct
                    delta_color = (
                        "#00D09C" if delta > 0.005
                        else "#FF4B4B" if delta < -0.005
                        else "#888"
                    )
                    is_new = d["id"] is None
                    tag = " <span style='color:#FCA5A5; font-size:0.75rem'>NEW</span>" if is_new else ""
                    full_rows.append(
                        f"<tr>"
                        f"<td style='padding:4px 12px'><b>{tkr}</b>{tag}</td>"
                        f"<td style='padding:4px 12px; color:#aaa'>{d['name']}</td>"
                        f"<td style='padding:4px 12px; color:#888'>{d['layer']}</td>"
                        f"<td style='padding:4px 12px; text-align:right'>{current_pct:.2f}%</td>"
                        f"<td style='padding:4px 12px; text-align:right; font-weight:600'>{after_pct:.2f}%</td>"
                        f"<td style='padding:4px 12px; text-align:right; color:{delta_color}'>{delta:+.2f}%</td>"
                        f"</tr>"
                    )
                # Cash row
                cash_delta = proj_cash_drifted - cash_before
                cash_color = "#00D09C" if cash_delta > 0.005 else "#FF4B4B" if cash_delta < -0.005 else "#888"
                full_rows.append(
                    f"<tr style='border-top:1px solid rgba(255,255,255,0.15)'>"
                    f"<td style='padding:4px 12px; font-style:italic'>CASH</td>"
                    f"<td style='padding:4px 12px; color:#aaa; font-style:italic'>Cash USD</td>"
                    f"<td style='padding:4px 12px; color:#888'>—</td>"
                    f"<td style='padding:4px 12px; text-align:right'>{cash_before:.2f}%</td>"
                    f"<td style='padding:4px 12px; text-align:right; font-weight:600'>{proj_cash_drifted:.2f}%</td>"
                    f"<td style='padding:4px 12px; text-align:right; color:{cash_color}'>{cash_delta:+.2f}%</td>"
                    f"</tr>"
                )
                full_table = (
                    "<table style='width:100%; border-collapse:collapse'>"
                    "<thead><tr style='color:#888; border-bottom:1px solid rgba(255,255,255,0.1)'>"
                    "<th style='padding:6px 12px; text-align:left'>Ticker</th>"
                    "<th style='padding:6px 12px; text-align:left'>Name</th>"
                    "<th style='padding:6px 12px; text-align:left'>Layer</th>"
                    "<th style='padding:6px 12px; text-align:right'>Current %</th>"
                    "<th style='padding:6px 12px; text-align:right'>After %</th>"
                    "<th style='padding:6px 12px; text-align:right'>Δ</th>"
                    "</tr></thead><tbody>"
                    + "".join(full_rows)
                    + "</tbody></table>"
                )
                st.markdown(full_table, unsafe_allow_html=True)

            st.caption("⚠️ Prices will be re-fetched at commit (final entry/exit price = live at commit time).")

            reason = st.text_input(
                "Reason (optional, recorded in History)",
                key=f"moves_reason_{_pid}",
            )

            cbc1, cbc2 = st.columns(2)
            with cbc1:
                if st.button("Cancel", key="moves_cancel"):
                    st.session_state.pop(confirm_key, None)
                    st.rerun()
            with cbc2:
                if st.button("Confirm & execute moves", type="primary", key="moves_commit"):
                    fresh_prices = get_prices_live(move_tickers)
                    # PRU model: recompute auto-conversion at commit time with fresh prices
                    commit_rebalance = _pru_compute_rebalance(
                        positions, st.session_state[draft_key], fresh_prices,
                    )
                    if commit_rebalance is None:
                        st.error("Targets unsolvable at commit. Aborted.")
                        st.stop()
                    errors   = []
                    executed = 0
                    for m in commit_rebalance["moves"]:
                        px = (fresh_prices.get(m["ticker"]) or {}).get("price") or m.get("current_price")
                        if not px:
                            errors.append(f"{m['ticker']}: no live price")
                            continue
                        try:
                            action = m["action"]
                            if action == "NOOP":
                                continue
                            elif action == "CLOSE":
                                close_position(m["id"], px, today_str,
                                               reason or "Move from cockpit")
                            elif action == "REDUCE":
                                # PRU semantics: entry_price preserved, trim DB by delta
                                trim_position(m["id"], abs(m["delta_db"]), px, today_str,
                                              reason or "Move from cockpit")
                            elif action == "REINFORCE":
                                # PRU averaging via add_position with the DB-weight delta
                                add_position({
                                    "ticker":       m["ticker"], "name": m["name"], "isin": None,
                                    "layer":        m["layer"],
                                    "weight":       m["delta_db"],
                                    "entry_price":  px,
                                    "entry_date":   today_str,
                                    "sector":       m["sector"],
                                    "geography":    m["geography"],
                                    "thematic":     m["thematic"],
                                    "thesis_short": "",
                                    "is_active":    True,
                                }, portfolio_id=_pid)
                            elif action == "BUY":
                                add_position({
                                    "ticker":       m["ticker"], "name": m["name"], "isin": None,
                                    "layer":        m["layer"],
                                    "weight":       m["new_db"],
                                    "entry_price":  px,
                                    "entry_date":   today_str,
                                    "sector":       m["sector"],
                                    "geography":    m["geography"],
                                    "thematic":     m["thematic"],
                                    "thesis_short": "",
                                    "is_active":    True,
                                }, portfolio_id=_pid)
                            executed += 1
                        except Exception as e:
                            errors.append(f"{m['ticker']}: {e}")

                    if errors:
                        st.error(f"{executed} executed, {len(errors)} failed: {'; '.join(errors)}")
                    else:
                        st.success(f"✓ {executed} move(s) executed.")

                    st.session_state.pop(confirm_key, None)
                    st.session_state.pop(draft_key, None)
                    st.session_state[ver_key] += 1
                    st.cache_data.clear()
                    st.rerun()

# ── HISTORY ───────────────────────────────────────────────────────────────────
with tab_history:
    txns = get_transactions(portfolio_id=_pid)
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
