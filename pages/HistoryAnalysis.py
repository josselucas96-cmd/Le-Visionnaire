import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import date

from utils.data import get_positions, get_transactions
from utils.market import get_history
from utils.metrics import build_portfolio_index
from utils.nav import render_nav

st.set_page_config(
    page_title="History Analysis | Le Visionnaire",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
    [data-testid="stSidebar"] { display: none; }
    .block-container { padding-top: 3.5rem; padding-bottom: 2rem; }
    [data-testid="stExpander"] summary p {
        font-size: 1.2rem !important;
        font-weight: 800 !important;
    }
</style>
""", unsafe_allow_html=True)

render_nav("history")

DARK_BG   = "#0E1117"
GRID_COL  = "#1F2633"
ACTION_COLORS = {
    "IN":     "#00D09C",
    "OUT":    "#FF4B4B",
    "SWITCH": "#4B9EFF",
    "TRIM":   "#FFA500",
}
ACTION_LABELS = {
    "IN":     "Buy",
    "OUT":    "Sell",
    "SWITCH": "Switch",
    "TRIM":   "Trim",
}

POSITION_COLORS = [
    "#00D09C", "#4B9EFF", "#FFA500", "#FF4B4B", "#A78BFA",
    "#34D399", "#F472B6", "#60A5FA", "#FBBF24", "#F87171",
    "#818CF8",
]

# ── Load data ─────────────────────────────────────────────────────────────────
all_positions  = get_positions(active_only=False)
active_pos     = [p for p in all_positions if p.get("is_active")]
transactions   = get_transactions()

if not all_positions:
    st.info("No positions yet.")
    st.stop()

chart_start = min(p["entry_date"] for p in all_positions if p.get("entry_date"))
all_tickers = tuple(set(p["ticker"] for p in all_positions))
history     = get_history(all_tickers, chart_start)

if history.empty:
    st.warning("Unable to load price history.")
    st.stop()

today_ts = pd.Timestamp(date.today())

# Portfolio index (active positions only, for the perf line)
port_index = build_portfolio_index(history, active_pos)
spy_raw    = history["SPY"].dropna() if "SPY" in history.columns else None
spy_index  = spy_raw / spy_raw.iloc[0] * 100 if spy_raw is not None else None

st.markdown(
    '<p style="font-size:2rem; font-weight:900; letter-spacing:-0.5px; margin-bottom:0.2rem;">'
    'History Analysis</p>',
    unsafe_allow_html=True,
)
st.caption("Portfolio moves, allocation drift, and position timeline.")
st.write("")

# ══════════════════════════════════════════════════════════════════════════════
# 1 — PERFORMANCE + ANNOTATIONS
# ══════════════════════════════════════════════════════════════════════════════
with st.expander("Performance & Moves", expanded=True):
    if port_index is not None and not port_index.empty:
        fig = go.Figure()

        # S&P 500 baseline
        if spy_index is not None:
            fig.add_trace(go.Scatter(
                x=spy_index.index, y=spy_index.values,
                name="S&P 500",
                line=dict(color="#555", width=1.5, dash="dot"),
                hovertemplate="%{x|%b %d, %Y}<br>S&P 500: %{y:.1f}<extra></extra>",
            ))

        # Portfolio line
        fig.add_trace(go.Scatter(
            x=port_index.index, y=port_index.values,
            name="Le Visionnaire",
            line=dict(color="#00D09C", width=2.5),
            hovertemplate="%{x|%b %d, %Y}<br>Portfolio: %{y:.1f}<extra></extra>",
        ))

        # Transaction markers
        for action, color in ACTION_COLORS.items():
            txn_subset = [t for t in transactions if t.get("action") == action]
            if not txn_subset:
                continue

            xs, ys, texts = [], [], []
            for t in txn_subset:
                ts = pd.Timestamp(t["date"])
                # Find nearest date in index
                idx = port_index.index.searchsorted(ts)
                idx = min(idx, len(port_index) - 1)
                nearest = port_index.index[idx]
                y_val = port_index.iloc[idx]

                # Build hover text
                if action == "IN":
                    label = f"<b>Buy {t.get('ticker_in','')}</b><br>{t.get('weight_in','')}% @ {t.get('price_in','')}"
                elif action == "OUT":
                    perf = t.get('perf_pct')
                    sign = "+" if perf and perf >= 0 else ""
                    label = (f"<b>Sell {t.get('ticker_out','')}</b><br>"
                             f"{t.get('weight_out','')}% @ {t.get('price_out','')}"
                             f"<br>Perf: {sign}{perf}%")
                elif action == "SWITCH":
                    label = (f"<b>Switch</b><br>"
                             f"OUT: {t.get('ticker_out','')} @ {t.get('price_out','')}<br>"
                             f"IN: {t.get('ticker_in','')} @ {t.get('price_in','')}")
                elif action == "TRIM":
                    perf = t.get('perf_pct')
                    sign = "+" if perf and perf >= 0 else ""
                    label = (f"<b>Trim {t.get('ticker_out','')}</b><br>"
                             f"−{t.get('weight_out','')}% @ {t.get('price_out','')}"
                             f"<br>Perf: {sign}{perf}%")
                else:
                    label = action

                if t.get("reason"):
                    label += f"<br><i>{t['reason'][:60]}</i>"

                xs.append(nearest)
                ys.append(y_val)
                texts.append(label)

            fig.add_trace(go.Scatter(
                x=xs, y=ys,
                mode="markers",
                name=ACTION_LABELS[action],
                marker=dict(color=color, size=12, symbol="circle",
                            line=dict(color="#0E1117", width=2)),
                hovertemplate="%{text}<extra></extra>",
                text=texts,
            ))

        fig.add_hline(y=100, line_dash="dash", line_color="#333", line_width=1)
        fig.update_layout(
            plot_bgcolor=DARK_BG, paper_bgcolor=DARK_BG,
            font=dict(color="#CCC"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            yaxis=dict(title="Base 100", gridcolor=GRID_COL, zeroline=False),
            xaxis=dict(gridcolor=GRID_COL),
            hovermode="closest",
            height=420,
            margin=dict(l=0, r=0, t=30, b=0),
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Not enough data to render the performance chart.")

# ══════════════════════════════════════════════════════════════════════════════
# 2 — STACKED AREA (allocation drift)
# ══════════════════════════════════════════════════════════════════════════════
with st.expander("Allocation Over Time", expanded=True):
    # Resample to weekly
    hist_w = history.resample("W").last()

    initial_cash = max(0.0, 100.0 - sum(float(p["weight"]) for p in all_positions
                                        if p.get("is_active")))

    # For each position, build a value series (only when active)
    position_values = {}
    for p in all_positions:
        ticker = p["ticker"]
        if ticker not in hist_w.columns:
            continue
        entry_ts  = pd.Timestamp(p["entry_date"])
        exit_ts   = pd.Timestamp(p["exit_date"]) if p.get("exit_date") else today_ts
        w_initial = float(p["weight"])

        series = hist_w[ticker].dropna()
        active = series[(series.index >= entry_ts) & (series.index <= exit_ts)]
        if active.empty:
            continue

        base = active.iloc[0]
        values = w_initial * active / base
        label = f"{ticker} ({p['name'].split()[0] if p.get('name') else ticker})"
        position_values[ticker] = {"series": values, "label": ticker}

    if position_values:
        all_dates = sorted(set().union(*[v["series"].index for v in position_values.values()]))
        df_vals = pd.DataFrame(index=all_dates)
        for ticker, info in position_values.items():
            df_vals[ticker] = info["series"].reindex(all_dates)
        df_vals = df_vals.fillna(0)
        df_vals["CASH"] = initial_cash

        total = df_vals.sum(axis=1)
        df_pct = df_vals.div(total, axis=0) * 100

        fig2 = go.Figure()

        # Cash first (bottom)
        colors_used = {}
        tickers_sorted = [c for c in df_pct.columns if c != "CASH"]
        # Sort by average weight descending for better visual
        avg_w = {t: df_pct[t].mean() for t in tickers_sorted}
        tickers_sorted = sorted(tickers_sorted, key=lambda t: avg_w[t], reverse=True)

        all_cols = tickers_sorted + ["CASH"]
        col_map  = {t: POSITION_COLORS[i % len(POSITION_COLORS)]
                    for i, t in enumerate(tickers_sorted)}
        col_map["CASH"] = "#2A3345"

        for i, ticker in enumerate(all_cols):
            if ticker not in df_pct.columns:
                continue
            series = df_pct[ticker]
            hover = [f"<b>{ticker}</b><br>{v:.1f}%<br>{d.strftime('%b %d, %Y')}<extra></extra>"
                     for d, v in zip(series.index, series.values)]
            fig2.add_trace(go.Scatter(
                x=series.index,
                y=series.values,
                name=ticker,
                mode="lines",
                stackgroup="one",
                line=dict(width=0.5, color=col_map[ticker]),
                fillcolor=col_map[ticker],
                hovertemplate=hover,
            ))

        fig2.update_layout(
            plot_bgcolor=DARK_BG, paper_bgcolor=DARK_BG,
            font=dict(color="#CCC"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
                        font=dict(size=10)),
            yaxis=dict(title="Allocation %", gridcolor=GRID_COL, range=[0, 100]),
            xaxis=dict(gridcolor=GRID_COL),
            hovermode="closest",
            height=380,
            margin=dict(l=0, r=0, t=30, b=0),
        )
        st.plotly_chart(fig2, use_container_width=True)
        st.caption("Weekly allocation based on live prices vs entry price. "
                   "Surfaces grow/shrink as positions appreciate or decline.")
    else:
        st.info("Not enough data to render the allocation chart.")

# ══════════════════════════════════════════════════════════════════════════════
# 3 — GANTT TIMELINE
# ══════════════════════════════════════════════════════════════════════════════
with st.expander("Position Timeline", expanded=True):
    fig3 = go.Figure()

    # Sort positions by entry_date then ticker
    sorted_pos = sorted(all_positions,
                        key=lambda p: (p.get("entry_date", ""), p.get("ticker", "")))

    today_str = date.today().isoformat()

    for i, p in enumerate(sorted_pos):
        entry = p.get("entry_date", today_str)
        exit_ = p.get("exit_date") or today_str
        is_active = p.get("is_active", True)
        ticker = p.get("ticker", "?")
        perf = None
        if p.get("exit_price") and p.get("entry_price"):
            perf = round((float(p["exit_price"]) - float(p["entry_price"]))
                         / float(p["entry_price"]) * 100, 2)

        color     = "#00D09C" if is_active else ("#FF4B4B" if perf and perf < 0 else "#4B9EFF")
        opacity   = 1.0 if is_active else 0.6
        end_label = "Active" if is_active else f"Closed {exit_}"
        perf_str  = f"  {'+' if perf and perf >= 0 else ''}{perf:.1f}%" if perf is not None else ""

        hover_text = (
            f"<b>{ticker}</b><br>"
            f"Entry: {entry} @ {p.get('entry_price', '?')}<br>"
            f"Exit: {end_label}{perf_str}<br>"
            f"Weight: {p.get('weight', '?')}%"
        )

        fig3.add_trace(go.Bar(
            x=[pd.Timestamp(exit_) - pd.Timestamp(entry)],
            y=[ticker],
            base=[pd.Timestamp(entry)],
            orientation="h",
            marker=dict(color=color, opacity=opacity, line=dict(width=0)),
            hovertemplate=hover_text + "<extra></extra>",
            showlegend=False,
            name=ticker,
        ))

        # Marker at entry
        fig3.add_trace(go.Scatter(
            x=[pd.Timestamp(entry)],
            y=[ticker],
            mode="markers",
            marker=dict(color="#00D09C", size=8, symbol="circle"),
            hoverinfo="skip",
            showlegend=False,
        ))

        # Marker at exit (if closed)
        if not is_active and p.get("exit_date"):
            fig3.add_trace(go.Scatter(
                x=[pd.Timestamp(p["exit_date"])],
                y=[ticker],
                mode="markers",
                marker=dict(color="#FF4B4B", size=8, symbol="circle"),
                hoverinfo="skip",
                showlegend=False,
            ))

    # Today line
    fig3.add_vline(
        x=pd.Timestamp(today_str).timestamp() * 1000,
        line_dash="dash", line_color="#444", line_width=1,
        annotation_text="Today",
        annotation_font_color="#666",
    )

    fig3.update_layout(
        plot_bgcolor=DARK_BG, paper_bgcolor=DARK_BG,
        font=dict(color="#CCC"),
        xaxis=dict(
            type="date",
            gridcolor=GRID_COL,
            title="",
        ),
        yaxis=dict(gridcolor=GRID_COL, autorange="reversed"),
        barmode="overlay",
        height=80 + len(sorted_pos) * 36,
        margin=dict(l=0, r=0, t=10, b=0),
        hovermode="closest",
    )
    st.plotly_chart(fig3, use_container_width=True)
    st.caption(
        "Green = active position · Red = closed at a loss · Blue = closed at a gain · "
        "Green dot = entry · Red dot = exit"
    )

# ── Disclaimer ────────────────────────────────────────────────────────────────
st.markdown("""
<div style="font-size:0.72rem; color:#333; margin-top:3rem;
            border-top:1px solid #1A1F26; padding-top:1rem; line-height:1.5;">
This page is for informational purposes only and does not constitute financial advice.
</div>
""", unsafe_allow_html=True)
