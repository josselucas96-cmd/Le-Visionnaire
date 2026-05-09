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
    add_position, close_position, trim_position, switch_position,
    get_setting, upsert_setting, reset_portfolio,
    get_events, add_event, delete_event,
    get_portfolios, get_portfolio, update_portfolio,
)
from utils.market import get_prices
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
_portfolios_admin = get_portfolios()
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
    "batisseur":   ("Le Bâtisseur",   "Quality Compounders + Tactical", "#F59E0B"),
    "nakamoto":    ("Le Nakamoto",    "Bitcoin Treasury Equities",      "#F97316"),
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

# ── Performance snapshot ──────────────────────────────────────────────────────
with st.expander("Performance", expanded=False):
    import plotly.graph_objects as go
    from utils.market import get_history, get_prices as _get_prices
    from utils.metrics import (build_portfolio_index, daily_returns, sharpe_ratio,
                               max_drawdown, beta_vs_spy, annualized_volatility, monthly_returns_table)
    from utils.theme import PORTFOLIO_LINE, BENCHMARK_LINE, HLINE_COLOR, BG, TEXT_MID, POSITIVE, NEGATIVE, TRIM
    _positions_perf = get_positions(portfolio_id=_pid)
    if _positions_perf:
        _inception = str(_pf.get("inception_date", "2026-04-01"))
        _bench_pri = _pf.get("benchmark_primary")
        _bench_pri_lbl = _pf.get("benchmark_primary_label") or _bench_pri or ""
        _bench_sec = _pf.get("benchmark_secondary")
        _bench_sec_lbl = _pf.get("benchmark_secondary_label") or _bench_sec or ""
        _accent = _pf.get("color_primary") or PORTFOLIO_LINE
        _portfolio_name = _pf.get("name", _pid)
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
        _bench_tickers = tuple(b for b in (_bench_pri, _bench_sec) if b)
        _history = get_history(_tickers_perf + _bench_tickers, _inception)
        _pri_perf = None
        _pri_index = None
        _sec_index = None
        if not _history.empty:
            _port_index = build_portfolio_index(_history, _positions_perf)
            if _bench_pri and _bench_pri in _history.columns:
                _pri_raw = _history[_bench_pri].dropna()
                if not _pri_raw.empty:
                    _pri_index = _pri_raw / _pri_raw.iloc[0] * 100
                    _pri_perf = round(_pri_index.iloc[-1] - 100, 2)
            if _bench_sec and _bench_sec in _history.columns:
                _sec_raw = _history[_bench_sec].dropna()
                if not _sec_raw.empty:
                    _sec_index = _sec_raw / _sec_raw.iloc[0] * 100
            _port_ret = daily_returns(_port_index)
            _bench_ret = daily_returns(_pri_index) if _pri_index is not None else pd.Series()
            _alpha = round(_port_perf - (_pri_perf or 0), 2)
            _today_valid = [p for p in _positions_perf if p.get("change_today") is not None]
            _today = sum(p["weight"] * p["change_today"] for p in _today_valid) / _total_w if _today_valid else None

            pc1, pc2, pc3, pc4 = st.columns(4)
            with pc1:
                s = "+" if _port_perf >= 0 else ""
                st.metric("Portfolio (inception)", f"{s}{_port_perf:.2f}%")
            with pc2:
                s = "+" if (_pri_perf or 0) >= 0 else ""
                st.metric(f"{_bench_pri_lbl} (inception)" if _bench_pri_lbl else "Benchmark (inception)",
                          f"{s}{_pri_perf:.2f}%" if _pri_perf is not None else "—")
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
                x=_port_index.index, y=_port_index.values, name=_portfolio_name,
                line=dict(color=_accent, width=3, shape="spline", smoothing=0.8),
                hovertemplate="%{x|%b %d, %Y}<br>Portfolio: %{y:.1f}<extra></extra>",
            ))
            if _pri_index is not None:
                _fig.add_trace(go.Scatter(
                    x=_pri_index.index, y=_pri_index.values, name=_bench_pri_lbl or _bench_pri,
                    line=dict(color=BENCHMARK_LINE, width=1.5, dash="dot", shape="spline", smoothing=0.6),
                    hovertemplate=f"%{{x|%b %d, %Y}}<br>{_bench_pri_lbl or _bench_pri}: %{{y:.1f}}<extra></extra>",
                ))
            if _sec_index is not None:
                _fig.add_trace(go.Scatter(
                    x=_sec_index.index, y=_sec_index.values, name=_bench_sec_lbl or _bench_sec,
                    visible="legendonly",
                    line=dict(color="#9CA3AF", width=1.5, dash="dash", shape="spline", smoothing=0.6),
                    hovertemplate=f"%{{x|%b %d, %Y}}<br>{_bench_sec_lbl or _bench_sec}: %{{y:.1f}}<extra></extra>",
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
                _beta_lbl = f"Beta vs {_bench_pri_lbl}" if _bench_pri_lbl else "Beta"
                b = beta_vs_spy(_port_ret, _bench_ret)
                st.metric(_beta_lbl, f"{b:.2f}" if b is not None else "—")

            # Monthly returns
            st.write("")
            st.markdown("**Monthly Returns (%)**")
            _mrt = monthly_returns_table(_port_index, inception_date=_inception)
            if not _mrt.empty:
                _MONTHS_ADM = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
                _inc_ts   = pd.Timestamp(_inception)
                _inc_col  = _MONTHS_ADM[_inc_ts.month - 1]
                _inc_year = _inc_ts.year

                def _color_m(col):
                    return ["color: #00D09C" if pd.notna(v) and v > 0
                            else "color: #FF4B4B" if pd.notna(v) and v < 0
                            else "" for v in col]
                _fmt = {m: (lambda v: f"{v:+.1f}" if pd.notna(v) else "") for m in _mrt.columns}
                _styled_mrt = _mrt.style.format(_fmt).apply(_color_m)
                if _inc_year in _mrt.index and _inc_col in _mrt.columns:
                    _styled_mrt = _styled_mrt.format(
                        lambda v: f"{v:+.1f}*" if pd.notna(v) else "",
                        subset=pd.IndexSlice[[_inc_year], [_inc_col]],
                    )
                st.dataframe(_styled_mrt,
                             use_container_width=True, height=38 + min(len(_mrt), 10) * 35)
                st.caption(f"\\* Partial month — return from inception ({_inception}) to month-end.")
    else:
        st.info("No positions to compute performance.")

st.divider()

# ── Active positions ──────────────────────────────────────────────────────────
positions = get_positions(portfolio_id=_pid)
st.subheader(f"Active Positions — {_pf.get('name', _pid)} ({len(positions)})")

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
    initial_capital = _read_initial_capital(_pid)
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

# ── Valo Tracking ─────────────────────────────────────────────────────────────
with st.expander(f"📐 Valo Tracking — {_pf.get('name', _pid)}", expanded=False):
    if not positions:
        st.info("No positions to evaluate.")
    else:
        from utils.market import get_valuation_fundamentals
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
                }, portfolio_id=_pid)
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
