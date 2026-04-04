import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

from utils.data import get_positions, get_setting
from utils.market import get_prices, get_history
from utils.metrics import (
    build_portfolio_index, daily_returns,
    sharpe_ratio, max_drawdown, beta_vs_spy,
    annualized_volatility, var_95, correlation_matrix, avg_pairwise_correlation,
    monthly_returns_table,
)
from utils.research import get_research
from utils.nav import render_nav

_published_count = len([p for p in get_research() if p["status"] == "published"])
papers_label = f"{_published_count} paper{'s' if _published_count != 1 else ''} published" if _published_count else "Coming soon"

st.set_page_config(
    page_title="Le Visionnaire",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

render_nav("app")

st.markdown("""
<style>
    [data-testid="stSidebar"] { display: none; }
    .block-container { padding-top: 3.5rem; padding-bottom: 2rem; }
    .portfolio-title { font-size: 3rem; font-weight: 900; letter-spacing: -1px; margin-bottom: 0; }
    .section-header { font-size: 1.5rem; font-weight: 800; letter-spacing: -0.3px; }
    [data-testid="stExpander"] summary p {
        font-size: 1.35rem !important;
        font-weight: 800 !important;
        letter-spacing: -0.3px !important;
    }
    .disclaimer { font-size: 0.72rem; color: #666; margin-top: 3rem;
                  border-top: 1px solid #222; padding-top: 1rem; line-height: 1.5; }
</style>
""", unsafe_allow_html=True)

# ── Data ──────────────────────────────────────────────────────────────────────
positions      = get_positions()
portfolio_name = get_setting("portfolio_name", "Le Visionnaire")
inception_date = get_setting("inception_date", "2026-04-01")

if not positions:
    st.title(portfolio_name)
    st.info("No positions loaded yet. Check back soon.")
    st.stop()

tickers = tuple(p["ticker"] for p in positions)
prices  = get_prices(tickers)

for p in positions:
    live = prices.get(p["ticker"], {})
    p["current_price"] = live.get("price")
    p["change_today"]  = live.get("change_pct")
    if p["current_price"] and p["entry_price"]:
        p["perf_pct"] = round(
            (p["current_price"] - p["entry_price"]) / p["entry_price"] * 100, 2
        )
    else:
        p["perf_pct"] = None

valid   = [p for p in positions if p["perf_pct"] is not None]
total_w = sum(p["weight"] for p in valid) or 1
portfolio_perf = sum(p["weight"] * p["perf_pct"] / total_w for p in valid)

chart_start = min(p["entry_date"] for p in positions if p.get("entry_date"))
history     = get_history(tickers, chart_start)

spy_perf  = None
spy_index = None

if not history.empty:
    port_index = build_portfolio_index(history, positions)
    if "SPY" in history.columns:
        spy_raw   = history["SPY"].dropna()
        spy_index = spy_raw / spy_raw.iloc[0] * 100
        spy_perf  = round(spy_index.iloc[-1] - 100, 2)
    last_updated = history.index[-1].strftime("%b %d, %Y")
else:
    port_index   = None
    last_updated = "—"

alpha = round(portfolio_perf - (spy_perf or 0), 2)

# ── Header ────────────────────────────────────────────────────────────────────
hcol1, hcol2 = st.columns([5, 1])
with hcol1:
    st.markdown(f'<p style="font-size:3rem; font-weight:900; letter-spacing:-1px; margin-bottom:0; line-height:1.1;">{portfolio_name}</p>', unsafe_allow_html=True)
    st.caption(
        f"Paper Portfolio · Inception {inception_date} · "
        f"{len(positions)} positions · Benchmark: S&P 500"
    )
with hcol2:
    st.markdown(
        f"<div style='text-align:right; padding-top:0.4rem;'>"
        f"<span style='font-size:0.7rem; color:#555;'>Last updated</span><br>"
        f"<span style='font-size:0.82rem; color:#888;'>{last_updated}</span></div>",
        unsafe_allow_html=True,
    )

st.write("")
metric_cols = st.columns(4)

with metric_cols[0]:
    sign = "+" if portfolio_perf >= 0 else ""
    st.metric("Portfolio (inception)", f"{sign}{portfolio_perf:.2f}%")
with metric_cols[1]:
    s = "+" if (spy_perf or 0) >= 0 else ""
    st.metric("S&P 500 (inception)", f"{s}{spy_perf:.2f}%" if spy_perf is not None else "—")
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

st.divider()

# ── Performance ───────────────────────────────────────────────────────────────
with st.expander("Performance", expanded=True):
    if port_index is not None and not port_index.empty:
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=port_index.index, y=port_index.values,
            name=portfolio_name,
            line=dict(color="#00D09C", width=2.5),
            hovertemplate="%{x|%b %d, %Y}<br>Portfolio: %{y:.1f}<extra></extra>",
        ))
        if spy_index is not None:
            fig.add_trace(go.Scatter(
                x=spy_index.index, y=spy_index.values,
                name="S&P 500",
                line=dict(color="#888888", width=1.5, dash="dot"),
                hovertemplate="%{x|%b %d, %Y}<br>S&P 500: %{y:.1f}<extra></extra>",
            ))
        fig.add_hline(y=100, line_dash="dash", line_color="#333", line_width=1)
        fig.update_layout(
            plot_bgcolor="#0E1117", paper_bgcolor="#0E1117",
            font=dict(color="#CCC"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            yaxis=dict(title="Base 100", gridcolor="#1F2633", zeroline=False),
            xaxis=dict(gridcolor="#1F2633"),
            hovermode="x unified",
            height=380,
            margin=dict(l=0, r=0, t=10, b=0),
        )
        st.plotly_chart(fig, use_container_width=True)

        port_ret = daily_returns(port_index)
        spy_ret  = daily_returns(spy_index) if spy_index is not None else pd.Series()

        r1, r2, r3 = st.columns(3)
        with r1:
            s = sharpe_ratio(port_ret)
            st.metric("Sharpe Ratio (ann.)", f"{s:.2f}" if s is not None else "—",
                      help="Annualized Sharpe, risk-free rate 5%")
        with r2:
            md = max_drawdown(port_index)
            st.metric("Max Drawdown", f"{md:.2f}%" if md is not None else "—")
        with r3:
            b = beta_vs_spy(port_ret, spy_ret)
            st.metric("Beta vs S&P 500", f"{b:.2f}" if b is not None else "—")

        # Monthly returns table
        st.write("")
        st.markdown("**Monthly Returns (%)**")
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
            st.dataframe(styled_mrt, use_container_width=True, height=38 + min(len(mrt), 10) * 35)

st.divider()

# ── Positions ─────────────────────────────────────────────────────────────────
with st.expander("Positions", expanded=True):
    df = pd.DataFrame(positions)
    display = df[[c for c in [
        "ticker", "name", "weight", "entry_price", "current_price",
        "perf_pct", "change_today", "sector", "geography", "thematic", "thesis_short"
    ] if c in df.columns]].rename(columns={
        "ticker":        "Ticker",
        "name":          "Name",
        "weight":        "Weight %",
        "entry_price":   "Entry",
        "current_price": "Price",
        "perf_pct":      "Perf %",
        "change_today":  "Today %",
        "sector":        "Sector",
        "geography":     "Geography",
        "thematic":      "Thematic",
        "thesis_short":  "Thesis",
    })

    def color_signed(col):
        return [
            "color: #00D09C" if isinstance(v, (int, float)) and v > 0
            else "color: #FF4B4B" if isinstance(v, (int, float)) and v < 0
            else "" for v in col
        ]

    styled = display.style.format({
        "Weight %": "{:.1f}%",
        "Entry":    lambda v: f"{v:.2f}" if isinstance(v, (int, float)) else "—",
        "Price":    lambda v: f"{v:.2f}" if isinstance(v, (int, float)) else "—",
        "Perf %":   lambda v: f"{v:+.2f}%" if isinstance(v, (int, float)) else "—",
        "Today %":  lambda v: f"{v:+.2f}%" if isinstance(v, (int, float)) else "—",
    }).apply(color_signed, subset=["Perf %", "Today %"])

    table_height = 38 + min(len(positions), 20) * 35
    st.dataframe(styled, use_container_width=True, hide_index=True, height=table_height)

    cash_pct_pub = round(max(0.0, 100.0 - display["Weight %"].sum()), 1)
    st.caption(f"CASH (USD) — {cash_pct_pub:.1f}%")

    st.write("")
    st.markdown(f"""
<div style="
    background: linear-gradient(135deg, #0D1F2D 0%, #0E1117 70%);
    border: 1px solid #1C2E3D;
    border-radius: 14px;
    padding: 2.2rem 2.4rem;
    margin: 1rem 0 0.5rem 0;
    position: relative;
    overflow: hidden;
">
    <div style="
        position: absolute; top: -50px; right: -50px;
        width: 220px; height: 220px;
        background: radial-gradient(circle, rgba(0,208,156,0.07) 0%, transparent 70%);
        border-radius: 50%;
    "></div>
    <div style="font-size:0.7rem; font-weight:700; letter-spacing:2px;
                color:#00D09C; text-transform:uppercase; margin-bottom:0.5rem;">
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
    background: #00D09C;
    color: #0E1117;
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

# ── Allocation ────────────────────────────────────────────────────────────────
with st.expander("Allocation", expanded=True):
    total_invested = display["Weight %"].sum()
    cash_pct = round(max(0, 100 - total_invested), 1)
    if cash_pct > 0:
        cash_row = pd.DataFrame([{
            "Ticker": "CASH", "Name": "Cash (USD)", "Weight %": cash_pct,
            "Entry": None, "Price": None, "Perf %": None, "Today %": None,
            "Sector": "Cash", "Geography": "USD", "Thematic": "Cash", "Thesis": "—",
        }])
        display_alloc = pd.concat([display, cash_row], ignore_index=True)
    else:
        display_alloc = display

    COLORS = px.colors.qualitative.Set2

    def donut_chart(df, col, title):
        grouped = df.groupby(col)["Weight %"].sum().reset_index()
        fig = px.pie(
            grouped, values="Weight %", names=col, title=title,
            hole=0.52, color_discrete_sequence=COLORS,
        )
        fig.update_traces(
            textinfo="percent",
            hovertemplate="%{label}: %{value:.1f}%<extra></extra>",
        )
        fig.update_layout(
            plot_bgcolor="#0E1117", paper_bgcolor="#0E1117",
            font=dict(color="#CCC"),
            margin=dict(l=0, r=0, t=40, b=0),
            legend=dict(font=dict(size=11)),
            title_font_size=14,
        )
        return fig

    a1, a2, a3 = st.columns(3)
    for col_name, title, container in [
        ("Sector",    "Sector",    a1),
        ("Geography", "Geography", a2),
        ("Thematic",  "Thematic",  a3),
    ]:
        if col_name in display_alloc.columns:
            with container:
                st.plotly_chart(donut_chart(display_alloc, col_name, title), use_container_width=True)

st.divider()

# ── Risk Analysis ─────────────────────────────────────────────────────────────
with st.expander("Risk Analysis", expanded=True):
    if port_index is not None and not port_index.empty:
        port_ret = daily_returns(port_index)
        spy_ret  = daily_returns(spy_index) if spy_index is not None else pd.Series()

        ra1, ra2, ra3, ra4 = st.columns(4)
        with ra1:
            pv = annualized_volatility(port_ret)
            st.metric("Portfolio Volatility (ann.)", f"{pv:.1f}%" if pv is not None else "—",
                      help="Annualized standard deviation of daily returns")
        with ra2:
            sv = annualized_volatility(spy_ret)
            st.metric("S&P 500 Volatility (ann.)", f"{sv:.1f}%" if sv is not None else "—")
        with ra3:
            v = var_95(port_ret)
            st.metric("VaR 95% (1-day)", f"{v:.2f}%" if v is not None else "—",
                      help="Historical VaR: worst daily loss in 95% of scenarios")
        with ra4:
            top3 = display.nlargest(3, "Weight %")[["Ticker", "Weight %"]]
            top3_pct = top3["Weight %"].sum()
            st.metric("Top 3 Concentration", f"{top3_pct:.1f}%",
                      help=" · ".join(top3["Ticker"].tolist()))

        corr    = correlation_matrix(history, positions)
        avg_corr = avg_pairwise_correlation(history, positions)
        if avg_corr is not None:
            if avg_corr < 0.3:
                corr_label, corr_color = "Low — well diversified", "#00D09C"
            elif avg_corr < 0.6:
                corr_label, corr_color = "Moderate", "#FFA500"
            else:
                corr_label, corr_color = "High — concentrated risk", "#FF4B4B"
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
            st.markdown("**Correlation Matrix** (daily returns, inception to date)")
            fig_corr = go.Figure(data=go.Heatmap(
                z=corr.values,
                x=corr.columns.tolist(),
                y=corr.index.tolist(),
                colorscale=[
                    [0.0, "#FF4B4B"],
                    [0.5, "#0E1117"],
                    [1.0, "#00D09C"],
                ],
                zmin=-1, zmax=1,
                text=corr.values.round(2),
                texttemplate="%{text}",
                textfont=dict(size=11),
                hovertemplate="%{y} / %{x}: %{z:.2f}<extra></extra>",
            ))
            fig_corr.update_layout(
                plot_bgcolor="#0E1117", paper_bgcolor="#0E1117",
                font=dict(color="#CCC"),
                height=380,
                margin=dict(l=0, r=0, t=10, b=0),
                xaxis=dict(side="bottom"),
            )
            st.plotly_chart(fig_corr, use_container_width=True)

# ── Disclaimer ────────────────────────────────────────────────────────────────
st.markdown("""
<div class="disclaimer">
<strong>Disclaimer:</strong> This is a paper trading simulation and does not involve real financial assets.
All content published here is for educational and informational purposes only and does not constitute
financial, investment, or legal advice. I am not a registered financial advisor. Investing in equities
involves significant risk, including the possible loss of principal. Always conduct your own due diligence
before making any investment decisions.
</div>
""", unsafe_allow_html=True)
