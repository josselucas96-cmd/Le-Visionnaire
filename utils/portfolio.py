"""Generic portfolio page renderer. Used by pages/Visionnaire.py, pages/Nakamoto.py, etc.

The function reads portfolio metadata from the `portfolios` Supabase table
(benchmark tickers, inception, name, etc.) and renders the full page.
Section visibility is controlled via the `options` dict.
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import date, timedelta

from utils.data import get_positions, get_setting, get_portfolio
from utils.market import get_prices, get_history, get_total_return_factor
from utils.metrics import (
    build_portfolio_index, daily_returns,
    sharpe_ratio, max_drawdown, beta_vs_spy,
    annualized_volatility, var_95, correlation_matrix, avg_pairwise_correlation,
    monthly_returns_table,
)
from utils.research import get_research
from utils.nav import render_nav
from utils.theme import (
    BG, ACCENT, POSITIVE, NEGATIVE, TRIM,
    TEXT_MID, PORTFOLIO_LINE, BENCHMARK_LINE, HLINE_COLOR,
    chart_layout,
)


# ── Color palettes (shared across portfolios) ────────────────────────────────
_THEMATIC_COLORS = {
    "AI / Semi":              "#1E40AF",
    "Crypto Currencies Play": "#F97316",
    "Biotech":                "#059669",
    "Space / Defense":        "#374151",
    "Consumer Growth":        "#FCA5A5",
    "Robotics / Automation":  "#6B7280",
    "Fintech / Payments":     "#60A5FA",
    "Energy Transition":      "#FCD34D",
    "Software / SaaS":        "#818CF8",
    "Cybersecurity":          "#F472B6",
    "Cloud / Infrastructure": "#6366F1",
    "Clean Energy":           "#4ADE80",
    "Digital Health":         "#34D399",
    "Social Platform":        "#F472B6",
    "EV / China":             "#86EFAC",
    "Other":                  "#94A3B8",
    "Cash":                   "#CBD5E1",
    "Cash/Equivalent":        "#CBD5E1",
}
_SECTOR_COLORS = {
    "Tech":          "#1E40AF",
    "Healthcare":    "#34D399",
    "Finance":       "#6366F1",
    "Communication": "#60A5FA",
    "Industrials":   "#6B7280",
    "Consumer":      "#FCD34D",
    "Energy":        "#FB923C",
    "Materials":     "#A8A29E",
    "Real Estate":   "#818CF8",
    "Utilities":     "#94A3B8",
    "Cash":          "#CBD5E1",
    "Cash/Equivalent": "#CBD5E1",
}
_GEO_COLORS = {
    "USA":              "#1E40AF",
    "Europe":           "#93C5FD",
    "Japan":            "#FDBA74",
    "Asia ex-Japan":    "#FDE68A",
    "China":            "#991B1B",
    "Emerging Markets": "#FCD34D",
    "LatAm":            "#86EFAC",
    "Global":           "#C084FC",
    "Other":            "#6B7280",
    "USD":              "#CBD5E1",
}
_LAYER_COLORS = {
    "Core":             "#1E40AF",
    "Conviction":       "#F97316",
    "Moonshot":         "#34D399",
    "Anchor":           "#1E40AF",
    "Exploratory":      "#F97316",
    "Income":           "#34D399",
    "Cash":             "#CBD5E1",
    "Cash/Equivalent":  "#CBD5E1",
}
_COLOR_MAPS = {
    "Sector":    _SECTOR_COLORS,
    "Geography": _GEO_COLORS,
    "Thematic":  _THEMATIC_COLORS,
    "Layer":     _LAYER_COLORS,
}

# Eyebrow text per portfolio (matches the IPS document tagline)
_EYEBROW = {
    "visionnaire": "HIGH CONVICTION EQUITY  ·  PAPER PORTFOLIO",
    "nakamoto":    "DIGITAL ASSET TREASURIES  ·  PAPER PORTFOLIO",
}


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    """Convert #RRGGBB to rgba(r, g, b, a) for CSS."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r}, {g}, {b}, {alpha})"


def _is_light_color(hex_color: str) -> bool:
    """Return True if the color is light (use dark text on it)."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return luminance > 0.55


def _donut_chart(df, col, title):
    grouped = df.groupby(col)["Alloc."].sum().reset_index()
    cmap = _COLOR_MAPS.get(col, {})
    color_map = {cat: cmap.get(cat, "#6B7280") for cat in grouped[col].unique()}
    fig = px.pie(
        grouped, values="Alloc.", names=col, title=title,
        hole=0.52, color=col, color_discrete_map=color_map,
    )
    fig.update_traces(
        textinfo="percent",
        hovertemplate="%{label}: %{value:.2f}%<extra></extra>",
    )
    fig.update_layout(
        plot_bgcolor=BG, paper_bgcolor=BG,
        font=dict(color=TEXT_MID),
        margin=dict(l=0, r=0, t=40, b=0),
        legend=dict(font=dict(size=11)),
        title_font_size=14,
    )
    return fig


def render_portfolio_page(portfolio_id: str, options: dict | None = None):
    """Render the full portfolio page for a given portfolio.

    Args:
        portfolio_id: slug, e.g. 'visionnaire' or 'nakamoto'
        options: section visibility config:
            show_donuts (list[str]): subset of {"Layer","Sector","Geography","Thematic"}
                                     default: all four
            show_risk_analysis (bool): default True
            show_research_teaser (bool): default True
            show_documents_section (bool): default True
            show_disclaimer_banner (bool): default True
    """
    options = options or {}
    show_donuts = options.get("show_donuts", ["Layer", "Sector", "Geography", "Thematic"])
    show_risk_analysis = options.get("show_risk_analysis", True)
    show_research_teaser = options.get("show_research_teaser", True)
    show_documents_section = options.get("show_documents_section", True)
    show_disclaimer_banner = options.get("show_disclaimer_banner", True)

    # ── Portfolio metadata ────────────────────────────────────────────────────
    pf = get_portfolio(portfolio_id)
    if not pf:
        st.error(f"Portfolio '{portfolio_id}' not found.")
        st.stop()

    portfolio_name = pf["name"]
    inception_date = str(pf["inception_date"])
    bench_pri      = pf.get("benchmark_primary")
    bench_pri_lbl  = pf.get("benchmark_primary_label") or bench_pri or ""
    bench_sec      = pf.get("benchmark_secondary")
    bench_sec_lbl  = pf.get("benchmark_secondary_label") or bench_sec or ""

    # ── Research papers count (for the research teaser label) ────────────────
    _published = [p for p in get_research()
                  if p["status"] in ("published", "locked")
                  and p.get("doc_type", "Stock Paper") == "Stock Paper"]
    _published_count = len(_published)
    papers_label = (f"{_published_count} paper{'s' if _published_count != 1 else ''} available"
                    if _published_count else "Research")

    # ── Top nav ───────────────────────────────────────────────────────────────
    render_nav(portfolio_id)

    # ── Disclaimer banner (collapsible, fixed) ───────────────────────────────
    if show_disclaimer_banner:
        accent_color = pf.get("color_primary") or "#A78BFA"
        accent_border = _hex_to_rgba(accent_color, 0.15)
        accent_border_light = _hex_to_rgba(accent_color, 0.10)
        st.markdown(f"""
<style>
.disc-wrap {{ margin: 0; padding: 0; }}
.disc-sum {{
    position: fixed;
    top: 0; right: 1.5rem;
    height: 52px;
    z-index: 9999999;
    display: flex;
    align-items: center;
    list-style: none;
    cursor: pointer;
    font-size: 0.6rem;
    color: #374151;
    user-select: none;
    padding: 0 0.4rem;
    gap: 4px;
}}
.disc-sum::-webkit-details-marker {{ display: none; }}
.disc-sum:hover {{ color: #6B7280; }}
.disc-wrap[open] .disc-sum::after {{ content: "▼ disclaimer"; }}
.disc-wrap:not([open]) .disc-sum::after {{ content: "▲ disclaimer"; }}
.disc-body {{
    position: fixed;
    top: 52px; left: 0; right: 0;
    z-index: 99998;
    background: rgba(6, 9, 18, 0.97);
    border-bottom: 1px solid {accent_border};
    padding: 0.45rem 2.5rem 0.5rem 2.5rem;
    font-size: 0.72rem;
    color: #7A8595;
    line-height: 1.5;
}}
@media (max-width: 768px) {{
    .disc-sum {{
        top: 85px; right: 0;
        height: 28px; width: 36px;
        justify-content: center;
        background: rgba(6,9,18,0.97);
        border-left: 1px solid {accent_border_light};
        border-bottom: 1px solid {accent_border_light};
        border-radius: 0 0 0 6px;
    }}
    .disc-wrap[open] .disc-sum::after {{ content: "✕"; }}
    .disc-wrap:not([open]) .disc-sum::after {{ content: "i"; }}
    .disc-body {{
        top: 85px;
        padding: 0.4rem 2.8rem 0.4rem 1rem;
        font-size: 0.65rem;
    }}
}}
</style>
<details class="disc-wrap" open>
<summary class="disc-sum"></summary>
<div class="disc-body">
<strong style="color:#9EAAB8;">Disclaimer</strong> —
{portfolio_name} is a personal paper portfolio shared for educational and informational purposes only.
It does not constitute investment advice or a recommendation to buy or sell any security or digital asset.
I am not a registered financial advisor. Past performance is not indicative of future results.
Always conduct your own due diligence before making any investment decision.
</div>
</details>
""", unsafe_allow_html=True)

    # ── Page styles (with portfolio-specific accent color) ───────────────────
    accent = pf.get("color_primary") or "#A78BFA"
    st.markdown(f"""
<style>
    [data-testid="stSidebar"] {{ display: none; }}
    .block-container {{ padding-top: 6.8rem; padding-bottom: 2rem; }}
    @media (max-width: 768px) {{
        .block-container {{ padding-top: 10rem !important; }}
    }}
    .portfolio-title {{ font-size: 3rem; font-weight: 900; letter-spacing: -1px; margin-bottom: 0; }}
    .section-header {{ font-size: 1.5rem; font-weight: 800; letter-spacing: -0.3px; }}
    [data-testid="stExpander"] summary p {{
        font-size: 1.35rem !important;
        font-weight: 800 !important;
        letter-spacing: -0.3px !important;
    }}
    .disclaimer {{ font-size: 0.72rem; color: #4A5568; margin-top: 3rem;
                  border-top: 1px solid #161D2E; padding-top: 1rem; line-height: 1.5; }}
    [data-testid="stRadio"] label div[data-testid="stMarkdownContainer"] {{ color: inherit; }}
    [data-baseweb="radio"] [data-checked="true"] div {{ background-color: {accent} !important; border-color: {accent} !important; }}
    [data-baseweb="radio"] div:focus-within {{ border-color: {accent} !important; }}

    /* ── Portfolio accent (IPS-inspired): eyebrow + title + metric labels ── */
    .pf-eyebrow {{
        color: {accent};
        font-size: 0.7rem;
        font-weight: 700;
        letter-spacing: 3px;
        text-transform: uppercase;
        margin-bottom: 0.7rem;
        margin-top: 0.2rem;
    }}
    .pf-title {{
        color: {accent} !important;
    }}
    /* Metric labels: accent, uppercase, letter-spaced (eyebrow style) */
    [data-testid="stMetric"] [data-testid="stMetricLabel"] p {{
        color: {accent} !important;
        text-transform: uppercase !important;
        letter-spacing: 1.5px !important;
        font-size: 0.68rem !important;
        font-weight: 700 !important;
    }}
    /* Metric values: stay bright white for contrast */
    [data-testid="stMetric"] [data-testid="stMetricValue"] {{
        color: #F9FAFB !important;
    }}
    .pf-section-label {{
        color: {accent} !important;
        font-weight: 700;
        font-size: 0.78rem;
        letter-spacing: 2px;
        text-transform: uppercase;
        margin-bottom: 0.6rem;
    }}

    /* Expander section headers: themed border instead of teal default */
    [data-testid="stExpander"] details {{
        border: 1px solid {_hex_to_rgba(accent, 0.25)} !important;
    }}
    [data-testid="stExpander"] details:hover {{
        border-color: {_hex_to_rgba(accent, 0.45)} !important;
    }}
    [data-testid="stExpander"] details[open] {{
        border-color: {accent} !important;
    }}
    [data-testid="stExpander"] summary:focus-visible {{
        outline: 2px solid {accent} !important;
        outline-offset: 2px;
    }}
    [data-testid="stExpander"] summary p {{
        color: #F9FAFB !important;
    }}
</style>
""", unsafe_allow_html=True)

    # ── Data ──────────────────────────────────────────────────────────────────
    positions = get_positions(portfolio_id=portfolio_id)
    if not positions:
        st.title(portfolio_name)
        st.info("No positions loaded yet. Check back soon.")
        st.stop()

    tickers = tuple(p["ticker"] for p in positions)
    prices  = get_prices(tickers)

    entry_dates    = tuple(p["entry_date"] for p in positions)
    entry_prices_t = tuple(float(p["entry_price"]) for p in positions)
    tr_factors     = get_total_return_factor(tickers, entry_dates, entry_prices_t)

    for p in positions:
        live = prices.get(p["ticker"], {})
        p["current_price"] = live.get("price")
        p["change_today"]  = live.get("change_pct")
        factor = tr_factors.get(p["ticker"], {"shares_factor": 1.0, "div_return_pct": 0.0})
        p["div_return"] = factor["div_return_pct"]
        if p["current_price"] and p["entry_price"]:
            price_return = (p["current_price"] - p["entry_price"]) / p["entry_price"] * 100
            total_return = (factor["shares_factor"] * p["current_price"] / p["entry_price"] - 1) * 100
            p["price_return"] = round(price_return, 2)
            p["perf_pct"]     = round(total_return, 2)
        else:
            p["perf_pct"]     = None
            p["price_return"] = None
            p["div_return"]   = None

    valid   = [p for p in positions if p["perf_pct"] is not None]
    total_w = sum(p["weight"] for p in valid) or 1
    portfolio_perf = sum(p["weight"] * p["perf_pct"] / total_w for p in valid)

    # Dynamic weights
    initial_cash = max(0.0, 100.0 - sum(p["weight"] for p in positions))
    for p in positions:
        if p.get("current_price") and p.get("entry_price"):
            p["current_value"] = p["weight"] * (p["current_price"] / p["entry_price"])
        else:
            p["current_value"] = p["weight"]
    total_current_value = sum(p["current_value"] for p in positions) + initial_cash
    for p in positions:
        p["current_weight"] = round(p["current_value"] / total_current_value * 100, 2)
    current_cash_pct = round(initial_cash / total_current_value * 100, 1)

    chart_start = min(p["entry_date"] for p in positions if p.get("entry_date"))
    benchmarks  = tuple(b for b in [bench_pri, bench_sec] if b)
    history     = get_history(tickers, chart_start, benchmarks=benchmarks)

    # 1-year history for correlation (no benchmarks needed)
    corr_start   = (date.today() - timedelta(days=365)).isoformat()
    history_corr = get_history(tickers, corr_start, benchmarks=())

    # Build portfolio index + benchmark indices (parameterized)
    primary_perf  = None
    primary_index = None
    secondary_perf  = None
    secondary_index = None

    if not history.empty:
        port_index = build_portfolio_index(history, positions)
        if bench_pri and bench_pri in history.columns:
            raw = history[bench_pri].dropna()
            if not raw.empty:
                primary_index = raw / raw.iloc[0] * 100
                primary_perf  = round(primary_index.iloc[-1] - 100, 2)
        if bench_sec and bench_sec in history.columns:
            raw = history[bench_sec].dropna()
            if not raw.empty:
                secondary_index = raw / raw.iloc[0] * 100
                secondary_perf  = round(secondary_index.iloc[-1] - 100, 2)
        last_updated = history.index[-1].strftime("%b %d, %Y") if not history.empty else "—"
    else:
        port_index   = None
        last_updated = "—"

    # Use chart's base-100 method for the headline metric (consistent with chart)
    if port_index is not None and not port_index.empty:
        portfolio_perf = round(float(port_index.iloc[-1] - 100), 2)

    alpha = round(portfolio_perf - (primary_perf or 0), 2)

    _n_returns = len(port_index.pct_change().dropna()) if (port_index is not None and not port_index.empty) else 0
    _MIN_DAYS_STATS = 60

    # ── Header ────────────────────────────────────────────────────────────────
    hcol1, hcol2 = st.columns([5, 1])
    with hcol1:
        eyebrow = _EYEBROW.get(portfolio_id, "PAPER PORTFOLIO")
        st.markdown(
            f'<div class="pf-eyebrow">{eyebrow}</div>'
            f'<p class="pf-title" style="font-family:\'Cormorant Garamond\', Georgia, serif; '
            f'font-size:3.5rem; font-weight:700; letter-spacing:-1px; '
            f'margin-bottom:0; line-height:1.1;">{portfolio_name}</p>',
            unsafe_allow_html=True,
        )
        st.caption(
            f"Inception {inception_date} · {len(positions)} positions · "
            f"Benchmark: {bench_pri_lbl}"
        )
    with hcol2:
        st.markdown(
            f"<div style='text-align:right; padding-top:0.4rem;'>"
            f"<span style='font-size:0.7rem; color:#555;'>Last updated</span><br>"
            f"<span style='font-size:0.82rem; color:#888;'>{last_updated}</span></div>",
            unsafe_allow_html=True,
        )

    metric_cols = st.columns(4)
    with metric_cols[0]:
        sign = "+" if portfolio_perf >= 0 else ""
        st.metric("Portfolio (inception)", f"{sign}{portfolio_perf:.2f}%")
    with metric_cols[1]:
        s = "+" if (primary_perf or 0) >= 0 else ""
        st.metric(f"{bench_pri_lbl} (inception)",
                  f"{s}{primary_perf:.2f}%" if primary_perf is not None else "—")
    with metric_cols[2]:
        a = "+" if alpha >= 0 else ""
        st.metric("Alpha", f"{a}{alpha:.2f}%")
    with metric_cols[3]:
        today_valid = [p for p in positions if p["change_today"] is not None]
        if today_valid:
            avg_today = sum(p["weight"] * p["change_today"] for p in today_valid) / total_w
            s = "+" if avg_today >= 0 else ""
            st.metric("Today", f"{s}{avg_today:.2f}%")
        else:
            st.metric("Today", "—")

    # ── Performance ───────────────────────────────────────────────────────────
    with st.expander("Performance", expanded=True):
        if port_index is not None and not port_index.empty:
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=port_index.index, y=port_index.values,
                name=portfolio_name,
                line=dict(color=accent, width=3, shape="spline", smoothing=0.8),
                hovertemplate="%{x|%b %d, %Y}<br>Portfolio: %{y:.1f}<extra></extra>",
            ))
            # Secondary benchmark (legend-only by default) — light grey
            if secondary_index is not None:
                fig.add_trace(go.Scatter(
                    x=secondary_index.index, y=secondary_index.values,
                    name=bench_sec_lbl,
                    visible="legendonly",
                    line=dict(color="#6B7280", width=1.5, dash="dot",
                              shape="spline", smoothing=0.6),
                    hovertemplate=f"%{{x|%b %d, %Y}}<br>{bench_sec_lbl}: %{{y:.1f}}<extra></extra>",
                ))
            # Primary benchmark (visible by default) — light, dashed
            if primary_index is not None:
                fig.add_trace(go.Scatter(
                    x=primary_index.index, y=primary_index.values,
                    name=bench_pri_lbl,
                    visible=True,
                    line=dict(color="#9CA3AF", width=1.5, dash="dash",
                              shape="spline", smoothing=0.6),
                    hovertemplate=f"%{{x|%b %d, %Y}}<br>{bench_pri_lbl}: %{{y:.1f}}<extra></extra>",
                ))
            fig.add_hline(y=100, line_dash="dash", line_color=HLINE_COLOR, line_width=1)
            layout = chart_layout(height=380)
            layout["hovermode"] = "x unified"
            layout["yaxis"]["title"] = "Base 100"
            layout["legend"] = dict(
                orientation="h",
                yanchor="top", y=-0.18,
                xanchor="center", x=0.5,
                font=dict(size=10),
                bgcolor="rgba(0,0,0,0)",
            )
            layout["margin"]["b"] = 60
            fig.update_layout(**layout)
            st.plotly_chart(fig, use_container_width=True)

            port_ret = daily_returns(port_index)
            secondary_ret = daily_returns(secondary_index) if secondary_index is not None else pd.Series()

            r1, r2, r3 = st.columns(3)
            _stats_ready = _n_returns >= _MIN_DAYS_STATS
            _stats_help = f"Available after {_MIN_DAYS_STATS} trading days (currently {_n_returns})"
            with r1:
                if _stats_ready:
                    s = sharpe_ratio(port_ret)
                    st.metric("Sharpe Ratio (ann.)",
                              f"{s:.2f}" if s is not None else "—",
                              help="Annualized Sharpe, risk-free rate 5%")
                else:
                    st.metric("Sharpe Ratio (ann.)", "—", help=_stats_help)
            with r2:
                md = max_drawdown(port_index)
                st.metric("Max Drawdown",
                          f"{md:.2f}%" if md is not None else "—")
            with r3:
                beta_label = f"Beta vs {bench_sec_lbl}" if bench_sec_lbl else "Beta"
                if _stats_ready:
                    b = beta_vs_spy(port_ret, secondary_ret)
                    st.metric(beta_label,
                              f"{b:.2f}" if b is not None else "—")
                else:
                    st.metric(beta_label, "—", help=_stats_help)

            # Monthly returns
            st.write("")
            st.markdown('<div class="pf-section-label">Monthly Returns (%)</div>', unsafe_allow_html=True)
            mrt = monthly_returns_table(port_index)
            if not mrt.empty:
                def color_monthly(col):
                    return [
                        "color: #00D09C" if pd.notna(v) and v > 0
                        else "color: #FF4B4B" if pd.notna(v) and v < 0
                        else "" for v in col
                    ]
                fmt = {m: lambda v: f"{v:+.1f}" if pd.notna(v) else "" for m in mrt.columns}
                styled_mrt = mrt.style.format(fmt).apply(color_monthly)
                st.dataframe(styled_mrt, use_container_width=True,
                             height=38 + min(len(mrt), 10) * 35)

    st.divider()

    # ── Positions ─────────────────────────────────────────────────────────────
    with st.expander("Positions", expanded=True):
        df = pd.DataFrame(positions)
        df = df.sort_values("current_weight", ascending=False)
        display = df[[c for c in [
            "ticker", "name", "layer", "current_weight", "entry_price", "current_price",
            "perf_pct", "change_today",
            "sector", "geography", "thematic", "thesis_short"
        ] if c in df.columns]].rename(columns={
            "ticker":         "Ticker",
            "name":           "Name",
            "layer":          "Layer",
            "current_weight": "Alloc.",
            "entry_price":    "Entry",
            "current_price":  "Price",
            "perf_pct":       "Total Return",
            "change_today":   "Today %",
            "sector":         "Sector",
            "geography":      "Geography",
            "thematic":       "Thematic",
            "thesis_short":   "Thesis",
        })
        display = display.drop(columns=["Thesis"], errors="ignore")

        def color_signed(col):
            return [
                f"color: {POSITIVE}" if isinstance(v, (int, float)) and v > 0
                else f"color: {NEGATIVE}" if isinstance(v, (int, float)) and v < 0
                else "" for v in col
            ]

        _numeric_cols = {"Alloc.", "Entry", "Price", "Total Return", "Today %"}
        empty_row = pd.DataFrame([{
            c: None if c in _numeric_cols else "" for c in display.columns
        }])
        cash_row_table = pd.DataFrame([{
            "Ticker": "CASH", "Name": "Cash USD", "Layer": "Cash",
            "Alloc.": current_cash_pct,
            "Entry": None, "Price": None,
            "Total Return": None, "Today %": None,
            "Sector": "—", "Geography": "USD", "Thematic": "—",
        }])
        display_full = pd.concat([display, empty_row, cash_row_table], ignore_index=True)

        styled = display_full.style.format({
            "Alloc.":       lambda v: f"{v:.2f}%" if isinstance(v, (int, float)) else "",
            "Entry":        lambda v: f"{v:.2f}" if isinstance(v, (int, float)) else "—",
            "Price":        lambda v: f"{v:.2f}" if isinstance(v, (int, float)) else "—",
            "Total Return": lambda v: f"{v:+.2f}%" if isinstance(v, (int, float)) else "—",
            "Today %":      lambda v: f"{v:+.2f}%" if isinstance(v, (int, float)) else "—",
        }).apply(color_signed, subset=["Total Return", "Today %"])

        table_height = 38 + (len(display) + 3) * 35
        st.dataframe(styled, use_container_width=True, hide_index=True, height=table_height)
        st.caption(f"Cash / Equivalent — Current: {current_cash_pct:.1f}%")

        # Research teaser (optional)
        if show_research_teaser:
            st.write("")
            accent_radial = _hex_to_rgba(accent, 0.10)
            accent_border_subtle = _hex_to_rgba(accent, 0.18)
            btn_text_color = "#0E1117" if _is_light_color(accent) else "#FFFFFF"
            st.markdown(f"""
<div style="
    background: linear-gradient(135deg, rgba(255,255,255,0.02) 0%, #0E1117 70%);
    border: 1px solid {accent_border_subtle};
    border-radius: 14px;
    padding: 2.2rem 2.4rem;
    margin: 1rem 0 0.5rem 0;
    position: relative;
    overflow: hidden;
">
    <div style="
        position: absolute; top: -50px; right: -50px;
        width: 220px; height: 220px;
        background: radial-gradient(circle, {accent_radial} 0%, transparent 70%);
        border-radius: 50%;
    "></div>
    <div style="font-size:0.7rem; font-weight:700; letter-spacing:2px;
                color:{accent}; text-transform:uppercase; margin-bottom:0.5rem;">
        Research · {papers_label}
    </div>
    <div style="font-size:1.6rem; font-weight:800; letter-spacing:-0.5px; margin-bottom:0.6rem;">
        Stock Papers
    </div>
    <div style="font-size:0.88rem; color:#888; line-height:1.65; max-width:480px;">
        In-depth equity analysis on portfolio positions and market themes.
    </div>
</div>
<a href="/Research" target="_self" style="
    display: inline-block;
    background: {accent};
    color: {btn_text_color};
    font-weight: 800;
    font-size: 0.95rem;
    padding: 0.65rem 1.6rem;
    border-radius: 8px;
    text-decoration: none;
    letter-spacing: 0.2px;
    margin-bottom: 0.5rem;
">Read the papers →</a>
""", unsafe_allow_html=True)

    st.divider()

    # ── Allocation ────────────────────────────────────────────────────────────
    with st.expander("Allocation", expanded=True):
        display_donut = display.copy()
        if current_cash_pct > 0:
            cash_row = pd.DataFrame([{
                "Ticker": "CASH", "Name": "Cash (USD)", "Layer": "Cash", "Alloc.": current_cash_pct,
                "Entry": None, "Price": None, "Total Return": None, "Today %": None,
                "Sector": "Cash/Equivalent", "Geography": "USD",
                "Thematic": "Cash/Equivalent",
            }])
            display_alloc = pd.concat([display_donut, cash_row], ignore_index=True)
        else:
            display_alloc = display_donut

        # Render only the donuts requested
        n_donuts = len([d for d in show_donuts if d == "Layer" or d in display_alloc.columns])
        if n_donuts > 0:
            cols = st.columns(n_donuts)
            i = 0
            for donut_type in show_donuts:
                if donut_type == "Layer":
                    if "Layer" in display_alloc.columns:
                        df_layer = display_alloc.copy()
                        df_layer["Layer"] = df_layer["Layer"].replace("Cash", "Cash/Equivalent")
                        grouped = df_layer.groupby("Layer")["Alloc."].sum().reset_index()
                        if not grouped.empty:
                            color_map = {c: _LAYER_COLORS.get(c, "#6B7280") for c in grouped["Layer"].unique()}
                            fig = px.pie(grouped, values="Alloc.", names="Layer", title="Portfolio Layer",
                                         hole=0.52, color="Layer", color_discrete_map=color_map)
                            fig.update_traces(textinfo="percent",
                                              hovertemplate="%{label}: %{value:.2f}%<extra></extra>")
                            fig.update_layout(plot_bgcolor=BG, paper_bgcolor=BG, font=dict(color=TEXT_MID),
                                              margin=dict(l=0, r=0, t=40, b=0),
                                              legend=dict(font=dict(size=11)), title_font_size=14)
                            with cols[i]:
                                st.plotly_chart(fig, use_container_width=True)
                            i += 1
                elif donut_type in display_alloc.columns:
                    with cols[i]:
                        st.plotly_chart(_donut_chart(display_alloc, donut_type, donut_type),
                                        use_container_width=True)
                    i += 1

    # ── Risk Analysis (optional) ──────────────────────────────────────────────
    if show_risk_analysis:
        st.divider()
        with st.expander("Risk Analysis", expanded=True):
            if port_index is not None and not port_index.empty:
                port_ret = daily_returns(port_index)
                secondary_ret = daily_returns(secondary_index) if secondary_index is not None else pd.Series()

                ra1, ra2, ra3, ra4 = st.columns(4)
                _stats_ready = _n_returns >= _MIN_DAYS_STATS
                _stats_help = f"Available after {_MIN_DAYS_STATS} trading days (currently {_n_returns})"
                with ra1:
                    if _stats_ready:
                        pv = annualized_volatility(port_ret)
                        st.metric("Portfolio Volatility (ann.)",
                                  f"{pv:.1f}%" if pv is not None else "—",
                                  help="Annualized standard deviation of daily returns")
                    else:
                        st.metric("Portfolio Volatility (ann.)", "—", help=_stats_help)
                with ra2:
                    sec_vol_label = f"{bench_sec_lbl} Volatility (ann.)" if bench_sec_lbl else "Benchmark Volatility (ann.)"
                    if _stats_ready:
                        sv = annualized_volatility(secondary_ret)
                        st.metric(sec_vol_label,
                                  f"{sv:.1f}%" if sv is not None else "—")
                    else:
                        st.metric(sec_vol_label, "—", help=_stats_help)
                with ra3:
                    if _stats_ready:
                        v = var_95(port_ret)
                        st.metric("VaR 95% (1-day)",
                                  f"{v:.2f}%" if v is not None else "—",
                                  help="Historical VaR: worst daily loss in 95% of scenarios")
                    else:
                        st.metric("VaR 95% (1-day)", "—", help=_stats_help)
                with ra4:
                    top3 = display.nlargest(3, "Alloc.")[["Ticker", "Alloc."]]
                    top3_pct = top3["Alloc."].sum()
                    st.metric("Top 3 Concentration", f"{top3_pct:.1f}%",
                              help=" · ".join(top3["Ticker"].tolist()) + " (current weights)")

                corr_mode = st.radio(
                    "Correlation window",
                    ["Trailing 12 months", "Since inception"],
                    horizontal=True, index=0, label_visibility="collapsed",
                )
                use_inception = corr_mode == "Since inception"
                h_for_corr = history if use_inception else history_corr
                corr     = correlation_matrix(h_for_corr, positions, inception=use_inception)
                avg_corr = avg_pairwise_correlation(h_for_corr, positions, inception=use_inception)
                if avg_corr is not None:
                    if avg_corr < 0.3:
                        corr_label, corr_color = "Low — well diversified", POSITIVE
                    elif avg_corr < 0.6:
                        corr_label, corr_color = "Moderate", TRIM
                    else:
                        corr_label, corr_color = "High — concentrated risk", NEGATIVE
                    st.markdown(
                        f"**Avg Pairwise Correlation** &nbsp; "
                        f"<span style='font-size:1.6rem; font-weight:800;'>{avg_corr}</span>"
                        f"&nbsp; <span style='color:{corr_color}; font-size:0.85rem;'>{corr_label}</span>"
                        f"<br><span style='font-size:0.75rem; color:#666;'>"
                        f"Average correlation between all position pairs. "
                        f"Closer to 0 = positions move independently (better diversification). "
                        f"Closer to 1 = positions move together (concentrated risk)."
                        f"</span>",
                        unsafe_allow_html=True,
                    )

                if not corr.empty:
                    label = "trailing 12 months" if not use_inception else "since inception"
                    st.markdown(f"**Correlation Matrix** (daily returns, {label})")
                    st.markdown(f"""
<style>
@media (max-width: 768px) and (orientation: portrait) {{
    .corr-rotate-hint {{ display: block !important; }}
}}
.corr-rotate-hint {{ display: none; }}
</style>
<div class="corr-rotate-hint" style="font-size:0.75rem; color:{accent}; margin-bottom:0.5rem;">
    Rotate your screen for a better view of the matrix.
</div>
""", unsafe_allow_html=True)
                    fig_corr = go.Figure(data=go.Heatmap(
                        z=corr.values,
                        x=corr.columns.tolist(),
                        y=corr.index.tolist(),
                        colorscale=[[0.0, NEGATIVE], [0.5, BG], [1.0, ACCENT]],
                        zmin=-1, zmax=1,
                        text=corr.values.round(2),
                        texttemplate="%{text}",
                        textfont=dict(size=11),
                        hovertemplate="%{y} / %{x}: %{z:.2f}<extra></extra>",
                    ))
                    fig_corr.update_layout(
                        plot_bgcolor=BG, paper_bgcolor=BG,
                        font=dict(color=TEXT_MID),
                        height=380,
                        margin=dict(l=0, r=0, t=10, b=0),
                        xaxis=dict(side="bottom"),
                    )
                    st.plotly_chart(fig_corr, use_container_width=True)

    # ── Documents (additional, non Stock Paper) ───────────────────────────────
    if show_documents_section:
        all_docs = [p for p in get_research() if p["status"] in ("published", "locked")]
        other_docs = [d for d in all_docs if d.get("doc_type", "Stock Paper") != "Stock Paper"]
        if other_docs:
            st.divider()
            with st.expander("Documents", expanded=True):
                st.markdown("**Other Documents**")
                for d in other_docs:
                    c1, c2 = st.columns([6, 1])
                    with c1:
                        st.markdown(
                            f"**{d['title']}**  \n"
                            f"<span style='font-size:0.78rem; color:#555;'>{d.get('published_at','')}"
                            f"{(' · ' + d['summary'][:80] + '…') if d.get('summary') else ''}</span>",
                            unsafe_allow_html=True,
                        )
                    with c2:
                        if d.get("file_url") and d["status"] == "published":
                            st.link_button("Open →", d["file_url"])
                        elif d["status"] == "locked":
                            st.markdown(
                                "<span style='display:inline-flex; align-items:center; gap:6px; "
                                "color:#6B7280; font-size:0.8rem; font-weight:600; letter-spacing:0.5px;'>"
                                "<svg xmlns='http://www.w3.org/2000/svg' width='18' height='18' "
                                "viewBox='0 0 24 24' fill='none' stroke='#6B7280' stroke-width='2' "
                                "stroke-linecap='round' stroke-linejoin='round'>"
                                "<rect x='3' y='11' width='18' height='11' rx='2' ry='2'></rect>"
                                "<path d='M7 11V7a5 5 0 0 1 10 0v4'></path></svg>RESTRICTED</span>",
                                unsafe_allow_html=True,
                            )
                    st.write("")

    # ── Bottom disclaimer ─────────────────────────────────────────────────────
    st.markdown("""
<div class="disclaimer">
<strong>Disclaimer:</strong> This is a paper trading simulation and does not involve real financial assets.
All content published here is for educational and informational purposes only and does not constitute
financial, investment, or legal advice. I am not a registered financial advisor. Investing involves
significant risk, including the possible loss of principal. Always conduct your own due diligence
before making any investment decisions.
</div>
""", unsafe_allow_html=True)
