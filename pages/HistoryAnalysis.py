import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import date

from utils.data import get_positions, get_transactions
from utils.market import get_history
from utils.metrics import build_portfolio_index
from utils.nav import render_nav
from utils.theme import (
    BG, GRID, BORDER, ACCENT, POSITIVE, NEGATIVE, SWITCH, TRIM,
    TEXT_MID, PORTFOLIO_LINE, BENCHMARK_LINE, HLINE_COLOR,
    CASH_COLOR, POSITION_COLORS, THEMATIC_COLORS, action_colors, chart_layout,
)

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


ACTION_COLORS  = action_colors()
ACTION_LABELS  = {"IN": "Buy", "OUT": "Sell", "SWITCH": "Switch", "TRIM": "Trim"}

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

# Portfolio index — use ALL positions (active + closed) for true historical perf
port_index = build_portfolio_index(history, all_positions)
spy_raw    = history["SPY"].dropna() if "SPY" in history.columns else None
spy_index  = spy_raw / spy_raw.iloc[0] * 100 if spy_raw is not None else None
qqq_raw    = history["QQQ"].dropna() if "QQQ" in history.columns else None
qqq_index  = qqq_raw / qqq_raw.iloc[0] * 100 if qqq_raw is not None else None

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

        if spy_index is not None:
            fig.add_trace(go.Scatter(
                x=spy_index.index, y=spy_index.values,
                name="S&P 500",
                visible=True,
                line=dict(color=BENCHMARK_LINE, width=1.5, dash="dot",
                          shape="spline", smoothing=0.6),
                hovertemplate="%{x|%b %d, %Y}<br>S&P 500: %{y:.1f}<extra></extra>",
            ))
        if qqq_index is not None:
            fig.add_trace(go.Scatter(
                x=qqq_index.index, y=qqq_index.values,
                name="Nasdaq 100",
                visible="legendonly",
                line=dict(color="#A78BFA", width=1.5, dash="dash",
                          shape="spline", smoothing=0.6),
                hovertemplate="%{x|%b %d, %Y}<br>Nasdaq 100: %{y:.1f}<extra></extra>",
            ))

        # Portfolio line
        fig.add_trace(go.Scatter(
            x=port_index.index, y=port_index.values,
            name="Le Visionnaire",
            line=dict(color=PORTFOLIO_LINE, width=3, shape="spline", smoothing=0.8),
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

        fig.add_hline(y=100, line_dash="dash", line_color=HLINE_COLOR, line_width=1)
        layout = chart_layout(height=420)
        layout["yaxis"]["title"] = "Base 100"
        fig.update_layout(**layout)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Not enough data to render the performance chart.")

# ══════════════════════════════════════════════════════════════════════════════
# 2 — STACKED AREA (allocation drift)
# ══════════════════════════════════════════════════════════════════════════════
with st.expander("Allocation Over Time", expanded=True):
    # Resample to weekly
    hist_w = history.resample("W").last()

    # Build per-position value series (only during active window)
    # Use a list to handle same ticker bought twice (e.g. NVDA sold and re-bought)
    pos_series_list = []
    for p in all_positions:
        ticker = p["ticker"]
        if ticker not in hist_w.columns:
            continue
        entry_ts  = pd.Timestamp(p["entry_date"])
        exit_ts   = pd.Timestamp(p["exit_date"]) if p.get("exit_date") else today_ts
        w_initial = float(p["weight"])

        series = hist_w[ticker].dropna()
        window = series[(series.index >= entry_ts) & (series.index <= exit_ts)]
        if window.empty:
            continue

        base   = window.iloc[0]
        values = w_initial * window / base
        # Unique label handles duplicate tickers
        label  = f"{ticker}_{p['id']}" if p.get("id") else ticker
        pos_series_list.append({
            "col": label,
            "ticker": ticker,
            "thematic": p.get("thematic", "Other"),
            "series": values,
        })

    if pos_series_list:
        all_dates = sorted(set().union(*[ps["series"].index for ps in pos_series_list]))
        df_vals = pd.DataFrame(index=all_dates)
        for ps in pos_series_list:
            df_vals[ps["col"]] = ps["series"].reindex(all_dates).fillna(0)

        # Dynamic cash: at each date, cash = 100 - sum of active position values
        df_vals["CASH"] = (100.0 - df_vals.sum(axis=1)).clip(lower=0)

        fig2 = go.Figure()

        pos_cols = [ps["col"] for ps in pos_series_list]
        avg_w    = {c: df_vals[c].mean() for c in pos_cols}
        pos_cols_sorted = sorted(pos_cols, key=lambda c: avg_w[c], reverse=True)

        # Map col → display ticker / thematic
        col_to_ticker   = {ps["col"]: ps["ticker"]   for ps in pos_series_list}
        col_to_thematic = {ps["col"]: ps["thematic"] for ps in pos_series_list}

        all_cols = pos_cols_sorted + ["CASH"]
        col_map  = {c: THEMATIC_COLORS.get(col_to_thematic.get(c, "Other"), "#6B7280")
                    for c in pos_cols_sorted}
        col_map["CASH"] = "#2A3345"

        for col in all_cols:
            if col not in df_vals.columns:
                continue
            display_name = col_to_ticker.get(col, col)
            series = df_vals[col]
            fig2.add_trace(go.Scatter(
                x=series.index,
                y=series.values,
                name=display_name,
                mode="lines",
                stackgroup="one",
                line=dict(width=0.5, color=col_map[col]),
                fillcolor=col_map[col],
                customdata=list(zip([display_name] * len(series), series.values)),
                hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]:.1f} pts<br>%{x|%b %d, %Y}<extra></extra>",
            ))

        layout2 = chart_layout(height=380)
        layout2["yaxis"]["title"] = "NAV (base 100)"
        fig2.update_layout(**layout2)
        st.plotly_chart(fig2, use_container_width=True)
        st.caption("Weekly NAV breakdown. Total height = portfolio value (base 100 at inception). "
                   "Each surface grows or shrinks as the position appreciates or declines.")
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

    layout3 = chart_layout(height=80 + len(sorted_pos) * 36)
    layout3["xaxis"]["type"] = "date"
    layout3["yaxis"]["autorange"] = "reversed"
    layout3["barmode"] = "overlay"
    fig3.update_layout(**layout3)
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
