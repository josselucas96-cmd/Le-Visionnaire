"""Generate Le Visionnaire / Le Nakamoto Monthly Report (HTML).

Usage:
    python generate_monthly_report.py            # defaults to Visionnaire
    python generate_monthly_report.py visionnaire
    python generate_monthly_report.py nakamoto

The HTML uses the portfolio's accent color from the `portfolios` table.
Output goes to: 01_THE PORTFOLIO PROJECT/Les portefeuilles/<Portfolio Name>/reports/.

To preview/export PDF: open the HTML in Chrome → Ctrl+P → 'Save as PDF',
A4 portrait, no margins, no headers/footers, enable background graphics.
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")
import base64
import io
import tomllib
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from supabase import create_client

# ── Common palette ────────────────────────────────────────────────────────────
DARK_BG     = "#0E1117"
DARK_PANEL  = "#13181F"
TEXT_LIGHT  = "#F9FAFB"
TEXT_MID    = "#9CA3AF"
TEXT_DIM    = "#6B7280"
POSITIVE    = "#00D09C"
NEGATIVE    = "#FF4B4B"

# ── Per-portfolio configuration ───────────────────────────────────────────────
CONFIGS = {
    "visionnaire": {
        "report_date":      "2026-04-30",
        "subfolder":        "Le Visionnaire",
        "risk_indicator":   6,
        "horizon":          "5 years minimum",
        "objective": (
            "Le Visionnaire is an unconstrained international equity paper portfolio focused "
            "on high-conviction, concentrated positions. It targets long-term outperformance of "
            "the Nasdaq 100 over rolling 5-year horizons, through rigorous selection of companies "
            "that compound shareholder value through innovation and structural differentiation."
        ),
        "market_comment": [
            "April 2026 was a resilient month for US equities despite mid-month volatility. The S&P 500 and Nasdaq 100 closed on modest gains, supported by the Q1 earnings season and the continued strength of US consumer spending.",
            "The Fed held its wait-and-see stance, with no rate cut this month. Markets now price in a single cut for 2026, down from two at the start of the year.",
            "Q1 earnings: positive-surprise ratio remains elevated, largely carried by the Magnificent 7. Sector dispersion stays wide — the signal of a more discriminating market.",
        ],
        "mgmt_comment": [
            "Le Visionnaire's inception was April 13. Over 17 trading days the portfolio is up +8.69%, ahead of the Nasdaq 100 by +0.53%. Too short a window to draw conclusions.",
            "<strong>Observation phase.</strong> We let the portfolio breathe to measure its real behaviour against the benchmarks. No management action this month.",
            "<strong>Benchmark convergence.</strong> Le Visionnaire trades at the top of its expected range versus the Nasdaq 100. The concentrated structure is expressing itself — no pathological divergence at this stage.",
            "<strong>Internal correlation monitoring.</strong> The sectoral concentration (Tech, Healthcare) calls for vigilance on common-factor risk. Pairwise correlation tracking is now active.",
        ],
    },
    "batisseur": {
        "report_date":      "2026-07-31",   # placeholder, update at launch
        "subfolder":        "Le Bâtisseur",
        "risk_indicator":   5,
        "horizon":          "5 years minimum",
        "objective": (
            "Le Bâtisseur is an unconstrained equity paper portfolio focused on quality compounding "
            "and capital allocation discipline. The core targets high-grade businesses, exceptional "
            "capital allocators, and category leaders, paired with a tactical layer of thematic plays "
            "and select opportunities. The portfolio is designed for long-term capital growth with "
            "rigorous risk management."
        ),
        "market_comment": [
            "Placeholder market commentary — to be drafted at portfolio launch.",
        ],
        "mgmt_comment": [
            "Le Bâtisseur is in pre-launch phase. The Investment Policy Statement and initial composition are under construction.",
        ],
    },
    "nakamoto": {
        "report_date":      "2026-05-02",
        "subfolder":        "Le Nakamoto",
        "risk_indicator":   7,
        "horizon":          "4 years minimum",
        "objective": (
            "Le Nakamoto is a digital-asset-treasury (DAT) paper portfolio designed to deliver "
            "amplified Bitcoin exposure through actively managed equity positions in companies "
            "holding BTC on their balance sheet. The portfolio aims to outperform Bitcoin spot "
            "over rolling 3- to 5-year horizons through rigorous DAT selection and tactical "
            "allocation between BTC DATs and an Income overlay."
        ),
        "market_comment": [
            "The Bitcoin ecosystem opened May 2026 with continued institutional flows and consolidating mNAV ratios across the DAT segment. BTC trades near the $100k mark, with macro liquidity conditions remaining supportive.",
            "Treasury operations across the DAT universe continue to mature. ATM-efficient programs, perpetual preferred issuances, and active capital structures increasingly separate the operationally robust names from passive accumulators.",
            "Geographic dispersion is widening. European and LatAm DAT segments are establishing distinct identities, beyond the US-centric dominance of recent quarters.",
        ],
        "mgmt_comment": [
            "Le Nakamoto's inception was May 1. Two trading days of history is too short for conclusions. The portfolio enters its first observation phase.",
            "<strong>Initial mode: Risk-on (default).</strong> ~100% allocation to BTC DATs, no Income overlay activated. Five anchor positions plus three exploratory names.",
            "<strong>Hard cap discipline.</strong> Single-position cap at 35% is respected at inception. The largest holding sits at 27%. Rotation will be triggered by mNAV cycle signals, not by calendar.",
            "<strong>Selection framework cleared.</strong> All eight names cleared the five-dimensional selection framework. None require operational re-evaluation in the first month.",
        ],
    },
}

# Project paths
PROJECT_ROOT = Path(r"C:\Users\USER\Desktop\Projet Claude\Claude Racine\01_THE PORTFOLIO PROJECT\Les portefeuilles")

# ── Data layer ────────────────────────────────────────────────────────────────
with open(".streamlit/secrets.toml", "rb") as f:
    secrets = tomllib.load(f)
sb = create_client(secrets["supabase_url"], secrets["supabase_key"])


def fetch_portfolio(portfolio_id):
    return sb.table("portfolios").select("*").eq("id", portfolio_id).execute().data[0]


def fetch_positions(portfolio_id):
    return (
        sb.table("positions")
        .select("*")
        .eq("portfolio_id", portfolio_id)
        .eq("is_active", True)
        .execute()
        .data
    )


def fetch_history(tickers: tuple, start: str, end: str, benchmarks: tuple) -> pd.DataFrame:
    all_t = list(set(list(tickers) + list(benchmarks)))
    raw = yf.download(all_t, start=start, end=end, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw["Close"]
    if raw.index.tz is not None:
        raw.index = raw.index.tz_localize(None)
    raw.index = pd.to_datetime(raw.index.date)
    return raw.dropna(how="all")


def fetch_live_prices(tickers: tuple) -> dict:
    out = {}
    for t in tickers:
        try:
            out[t] = float(yf.Ticker(t).fast_info.last_price)
        except Exception:
            out[t] = None
    return out


# ── Computations ──────────────────────────────────────────────────────────────
def build_index(history: pd.DataFrame, positions: list) -> pd.Series:
    total_w = sum(p["weight"] for p in positions) or 1
    portfolio = pd.Series(0.0, index=history.index)
    contributed = False
    for p in positions:
        t = p["ticker"]
        if t not in history.columns:
            continue
        w = p["weight"] / total_w
        s = history[t].dropna()
        if s.empty:
            continue
        ed = pd.Timestamp(p["entry_date"])
        after = s[s.index >= ed]
        if after.empty:
            continue
        base = after.iloc[0]
        norm_after = after / base * 100
        before_idx = s.index[s.index < ed]
        norm_before = pd.Series(100.0, index=before_idx)
        full = pd.concat([norm_before, norm_after]).reindex(history.index).ffill().bfill()
        portfolio += full * w
        contributed = True
    return portfolio if contributed else pd.Series(dtype=float)


def compute_position_metrics(positions: list, prices: dict) -> tuple[list, float]:
    total_w = sum(p["weight"] for p in positions) or 1
    for p in positions:
        cp = prices.get(p["ticker"])
        p["current_price"] = cp
        if cp and p["entry_price"]:
            p["perf_pct"] = round((cp - p["entry_price"]) / p["entry_price"] * 100, 2)
            p["contribution"] = round(p["weight"] * p["perf_pct"] / total_w, 3)
        else:
            p["perf_pct"] = None
            p["contribution"] = None

    initial_cash = max(0.0, 100.0 - sum(p["weight"] for p in positions))
    for p in positions:
        if p.get("current_price") and p.get("entry_price"):
            p["current_value"] = p["weight"] * (p["current_price"] / p["entry_price"])
        else:
            p["current_value"] = p["weight"]
    total_cv = sum(p["current_value"] for p in positions) + initial_cash
    for p in positions:
        p["current_weight"] = round(p["current_value"] / total_cv * 100, 2)
    cash_pct = round(initial_cash / total_cv * 100, 1)
    return positions, cash_pct


def aggregate_alloc(positions: list, key: str, cash_pct: float) -> list[tuple[str, float]]:
    df = pd.DataFrame(positions)
    if key not in df.columns:
        return []
    grouped = df.groupby(key)["current_weight"].sum().reset_index()
    grouped = grouped.sort_values("current_weight", ascending=False)
    out = [(row[key] or "—", round(row["current_weight"], 1)) for _, row in grouped.iterrows()]
    if cash_pct > 0:
        out.append(("Cash", cash_pct))
    return out


def max_drawdown(series: pd.Series) -> float | None:
    if series.empty:
        return None
    peak = series.cummax()
    dd = (series - peak) / peak * 100
    return round(dd.min(), 2)


# ── Chart ─────────────────────────────────────────────────────────────────────
def generate_chart_b64(history, port_index, portfolio_name, benchmarks: list[tuple[str, str, str]],
                      accent: str) -> str:
    """benchmarks: list of (ticker, label, line_style) tuples."""
    fig, ax = plt.subplots(figsize=(8.5, 3.4), dpi=130)
    fig.patch.set_facecolor(DARK_BG)
    ax.set_facecolor(DARK_BG)

    ax.plot(port_index.index, port_index.values, color=accent, linewidth=2.4,
            label=portfolio_name, zorder=3)

    grey_shades = ["#9CA3AF", "#6B7280"]
    for i, (ticker, label, style) in enumerate(benchmarks):
        if ticker not in history.columns:
            continue
        s = history[ticker].dropna()
        if s.empty:
            continue
        idx = s / s.iloc[0] * 100
        ax.plot(idx.index, idx.values, color=grey_shades[i % 2], linewidth=1.3,
                linestyle=style, label=label, zorder=2 - i)

    ax.axhline(100, color="#374151", linestyle="--", linewidth=0.6, zorder=0)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#374151")
    ax.spines["bottom"].set_color("#374151")
    ax.tick_params(colors=TEXT_MID, labelsize=8)
    ax.grid(True, color="#1F2937", linewidth=0.5, alpha=0.5, zorder=0)
    ax.set_ylabel("Base 100", color=TEXT_MID, fontsize=8)
    ax.legend(loc="upper left", fontsize=8, frameon=False, labelcolor=TEXT_LIGHT)

    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=DARK_BG, bbox_inches="tight", dpi=140)
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()


# ── HTML rendering ────────────────────────────────────────────────────────────
def render_html(ctx: dict) -> str:
    pf = ctx["portfolio"]
    cfg = ctx["config"]
    accent = pf.get("color_primary") or "#A78BFA"
    border = f"rgba({int(accent[1:3], 16)}, {int(accent[3:5], 16)}, {int(accent[5:7], 16)}, 0.18)"

    eyebrow_text = {
        "visionnaire": "HIGH CONVICTION EQUITY  ·  PAPER PORTFOLIO",
        "nakamoto":    "DIGITAL ASSET TREASURIES  ·  PAPER PORTFOLIO",
    }.get(ctx["portfolio_id"], "PAPER PORTFOLIO")

    period_label = pd.Timestamp(cfg["report_date"]).strftime("%B %Y")
    risk_idx = cfg["risk_indicator"]
    horizon  = cfg["horizon"]

    css = f"""
    @page {{ size: A4 portrait; margin: 12mm 14mm; }}
    * {{ box-sizing: border-box; }}
    html, body {{
        margin: 0; padding: 0;
        background: {DARK_BG};
        color: {TEXT_LIGHT};
        font-family: 'Helvetica Neue', 'Avenir Next', Avenir, Arial, sans-serif;
        font-size: 9.5px;
        line-height: 1.45;
    }}
    .page {{
        background: {DARK_BG};
        padding: 14mm 12mm;
        page-break-after: always;
        max-width: 210mm;
        margin: 0 auto;
        min-height: 297mm;
    }}
    .page:last-child {{ page-break-after: auto; }}
    h1, h2, h3 {{ font-family: 'Cormorant Garamond', Georgia, serif; margin: 0; color: {TEXT_LIGHT}; }}

    .top-band {{
        border-top: 2px solid {accent};
        padding-top: 6px;
        display: flex;
        justify-content: space-between;
        align-items: baseline;
        margin-bottom: 12px;
        font-size: 9px;
        color: {TEXT_MID};
        letter-spacing: 0.5px;
    }}
    .top-band b {{ color: {accent}; letter-spacing: 1px; }}

    .header-block {{ display: flex; justify-content: space-between; gap: 18px; margin-bottom: 12px; }}
    .header-left {{ flex: 1; }}
    .header-right {{ width: 200px; padding-left: 14px; border-left: 1px solid {border}; }}

    .eyebrow {{
        font-size: 8px;
        font-weight: 700;
        letter-spacing: 3px;
        color: {TEXT_MID};
        text-transform: uppercase;
        margin-bottom: 4px;
    }}
    .pf-title {{
        font-family: 'Cormorant Garamond', Georgia, serif;
        font-size: 28px;
        font-weight: 700;
        letter-spacing: -0.5px;
        color: {TEXT_LIGHT};
        line-height: 1;
        margin-bottom: 2px;
    }}
    .pf-subtitle {{
        font-family: 'Cormorant Garamond', Georgia, serif;
        font-size: 13px;
        font-style: italic;
        color: {accent};
        margin-bottom: 8px;
    }}
    .meta-row {{
        font-size: 8.5px;
        color: {TEXT_MID};
        letter-spacing: 0.4px;
        text-transform: uppercase;
    }}
    .meta-row b {{ color: {TEXT_LIGHT}; font-weight: 700; }}

    .risk-box {{
        background: {DARK_PANEL};
        border: 1px solid {border};
        border-radius: 4px;
        padding: 6px 8px;
        font-size: 8px;
    }}
    .risk-row {{ display: flex; gap: 4px; margin-top: 4px; }}
    .risk-cell {{
        flex: 1; text-align: center;
        background: #1A1F2A; padding: 3px 0;
        font-size: 8.5px; font-weight: 700;
        border-radius: 2px;
    }}
    .risk-cell.active {{ background: {accent}; color: {DARK_BG}; }}
    .risk-label {{
        display: flex; justify-content: space-between;
        font-size: 7.5px; color: {TEXT_DIM};
        text-transform: uppercase; letter-spacing: 0.5px;
        margin-bottom: 3px;
    }}
    .meta-table {{
        width: 100%;
        border-collapse: collapse;
        margin-top: 6px;
        font-size: 8.5px;
    }}
    .meta-table td {{ padding: 2px 0; color: {TEXT_MID}; }}
    .meta-table td:last-child {{ text-align: right; color: {TEXT_LIGHT}; font-weight: 600; }}

    .section-label {{
        color: {accent};
        text-transform: uppercase;
        letter-spacing: 1.8px;
        font-size: 8.5px;
        font-weight: 700;
        margin: 12px 0 5px 0;
        border-bottom: 1px solid {border};
        padding-bottom: 3px;
    }}
    .objective {{
        font-size: 9.5px;
        color: {TEXT_LIGHT};
        line-height: 1.55;
        margin-bottom: 4px;
    }}

    .two-col {{ display: flex; gap: 14px; margin-bottom: 6px; }}
    .col {{ flex: 1; }}
    .bullet-list {{ list-style: none; padding: 0; margin: 0; }}
    .bullet-list li {{
        position: relative;
        padding-left: 12px;
        margin-bottom: 4px;
        color: {TEXT_LIGHT};
        font-size: 9px;
        line-height: 1.5;
    }}
    .bullet-list li::before {{
        content: "▸";
        color: {accent};
        position: absolute;
        left: 0;
        font-size: 8px;
        top: 1px;
    }}
    .bullet-list li strong {{ color: {accent}; font-weight: 700; }}

    .chart-block {{ margin-top: 6px; padding: 4px 0; }}
    .chart-block img {{ width: 100%; display: block; }}

    .perf-table {{
        width: 100%;
        border-collapse: collapse;
        margin-top: 6px;
        font-size: 9px;
    }}
    .perf-table th {{
        background: {DARK_PANEL};
        color: {accent};
        text-transform: uppercase;
        letter-spacing: 1px;
        font-size: 7.5px;
        font-weight: 700;
        padding: 6px 5px;
        text-align: right;
        border-bottom: 1px solid {border};
    }}
    .perf-table th:first-child {{ text-align: left; }}
    .perf-table td {{
        padding: 5px 5px;
        border-bottom: 1px solid #1F2937;
        color: {TEXT_LIGHT};
        text-align: right;
    }}
    .perf-table td:first-child {{ text-align: left; color: {TEXT_MID}; }}
    .perf-table td.pos {{ color: {POSITIVE}; }}
    .perf-table td.neg {{ color: {NEGATIVE}; }}
    .perf-table td.bold {{ font-weight: 700; color: {TEXT_LIGHT}; }}
    .monthly-matrix th, .monthly-matrix td {{ font-size: 8px; padding: 4px 3px; }}
    .monthly-matrix th:first-child, .monthly-matrix td:first-child {{ width: 50px; }}

    .alloc-grid {{
        display: grid;
        grid-template-columns: 1fr 1fr 1fr;
        gap: 10px;
        margin-bottom: 8px;
    }}
    .alloc-table {{ width: 100%; border-collapse: collapse; font-size: 8.5px; }}
    .alloc-table caption {{
        text-align: left;
        color: {accent};
        text-transform: uppercase;
        letter-spacing: 1.2px;
        font-size: 8px;
        font-weight: 700;
        padding-bottom: 4px;
        margin-bottom: 2px;
        border-bottom: 1px solid {border};
    }}
    .alloc-table td {{ padding: 2px 0; }}
    .alloc-table td:last-child {{ text-align: right; color: {TEXT_LIGHT}; font-weight: 600; }}
    .alloc-table td.cat {{ color: {TEXT_MID}; }}

    .holdings-table, .contrib-table {{
        width: 100%;
        border-collapse: collapse;
        font-size: 8.5px;
        margin-top: 4px;
    }}
    .holdings-table th, .contrib-table th {{
        background: {DARK_PANEL};
        color: {accent};
        text-transform: uppercase;
        letter-spacing: 0.8px;
        font-size: 7px;
        font-weight: 700;
        padding: 5px 6px;
        text-align: left;
    }}
    .holdings-table th.r, .contrib-table th.r {{ text-align: right; }}
    .holdings-table td, .contrib-table td {{
        padding: 3.5px 6px;
        border-bottom: 1px solid #1F2937;
        color: {TEXT_LIGHT};
    }}
    .holdings-table td.r, .contrib-table td.r {{ text-align: right; }}
    .holdings-table td.dim, .contrib-table td.dim {{ color: {TEXT_MID}; }}
    .contrib-table td.pos {{ color: {POSITIVE}; font-weight: 600; }}
    .contrib-table td.neg {{ color: {NEGATIVE}; font-weight: 600; }}

    .risk-metrics-grid {{
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 8px;
        margin-top: 8px;
    }}
    .metric-card {{
        background: {DARK_PANEL};
        border: 1px solid {border};
        border-radius: 4px;
        padding: 6px 8px;
    }}
    .metric-card .label {{
        font-size: 7px;
        color: {accent};
        text-transform: uppercase;
        letter-spacing: 1px;
        font-weight: 700;
        margin-bottom: 2px;
    }}
    .metric-card .value {{ font-size: 13px; color: {TEXT_LIGHT}; font-weight: 700; }}
    .metric-card .sub {{ font-size: 7px; color: {TEXT_DIM}; margin-top: 1px; }}

    .footer {{
        margin-top: 14px;
        padding-top: 6px;
        border-top: 1px solid #1F2937;
        font-size: 7px;
        color: {TEXT_DIM};
        line-height: 1.5;
    }}
    .footer strong {{ color: {accent}; }}
    .page-num {{ text-align: right; font-size: 7.5px; color: {TEXT_DIM}; margin-top: 6px; }}
    """

    # Risk cells (1-7), highlight active
    risk_cells_html = "".join(
        f"<div class='risk-cell{' active' if i == risk_idx else ''}'>{i}</div>"
        for i in range(1, 8)
    )

    # Monthly returns matrix (year rows × 12 month columns)
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    perf_rows = ""
    for year, month_dict in sorted(ctx["monthly_returns"].items()):
        cells = ""
        for m_idx in range(1, 13):
            v = month_dict.get(m_idx)
            if v is None:
                cells += "<td>—</td>"
            else:
                cls = "pos" if v >= 0 else "neg"
                cells += f"<td class='{cls}'>{v:+.2f}%</td>"
        perf_rows += f"<tr><td class='bold'>{year}</td>{cells}</tr>"

    # Allocation tables
    def alloc_rows(items):
        return "".join(f"<tr><td class='cat'>{cat}</td><td>{w:.1f}%</td></tr>"
                       for cat, w in items)
    alloc_layer  = alloc_rows(ctx["alloc_layer"])
    alloc_sector = alloc_rows(ctx["alloc_sector"])
    alloc_geo    = alloc_rows(ctx["alloc_geo"])

    # Top 10 holdings
    holdings_rows = ""
    for p in ctx["top10"]:
        holdings_rows += (
            f"<tr><td><b>{p['ticker']}</b></td>"
            f"<td class='dim'>{p['name'][:24]}</td>"
            f"<td class='dim'>{p.get('geography') or '—'}</td>"
            f"<td class='dim'>{p.get('sector') or '—'}</td>"
            f"<td class='r'>{p['current_weight']:.2f}%</td></tr>"
        )

    # Top 5 contributors / detractors
    contrib_rows = ""
    for p in ctx["top5_contrib"]:
        contrib_rows += (
            f"<tr><td><b>{p['ticker']}</b></td>"
            f"<td class='dim'>{p['name'][:18]}</td>"
            f"<td class='r dim'>{p['current_weight']:.1f}%</td>"
            f"<td class='r pos'>+{p['contribution']:.2f}%</td></tr>"
        )
    detract_rows = ""
    for p in ctx["bottom5_contrib"]:
        cls = "neg" if p["contribution"] < 0 else "pos"
        sign = "" if p["contribution"] < 0 else "+"
        detract_rows += (
            f"<tr><td><b>{p['ticker']}</b></td>"
            f"<td class='dim'>{p['name'][:18]}</td>"
            f"<td class='r dim'>{p['current_weight']:.1f}%</td>"
            f"<td class='r {cls}'>{sign}{p['contribution']:.2f}%</td></tr>"
        )

    market_lis = "".join(f"<li>{b}</li>" for b in cfg["market_comment"])
    mgmt_lis   = "".join(f"<li>{b}</li>" for b in cfg["mgmt_comment"])
    chart_img  = f"data:image/png;base64,{ctx['chart_b64']}"

    html = f"""<!DOCTYPE html>
<html lang='en'>
<head>
<meta charset='utf-8'>
<title>{pf['name']} — Monthly Report — {cfg['report_date']}</title>
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@500;600;700&display=swap" rel="stylesheet">
<style>{css}</style>
</head>
<body>

<div class='page'>
  <div class='top-band'>
    <span><b>{pf['name'].upper()}</b> &nbsp;|&nbsp; Monthly Report</span>
    <span>Paper portfolio. Not financial advice. Personal views only.</span>
  </div>

  <div class='header-block'>
    <div class='header-left'>
      <div class='eyebrow'>{eyebrow_text}</div>
      <div class='pf-title'>{pf['name']}</div>
      <div class='pf-subtitle'>Monthly Report — {period_label}</div>
      <div class='meta-row'>
        Inception: <b>{pf['inception_date']}</b>
        &nbsp;·&nbsp; Reporting: <b>{cfg['report_date']}</b>
      </div>
    </div>
    <div class='header-right'>
      <div class='risk-box'>
        <div class='risk-label'><span>Lower risk</span><span>Higher risk</span></div>
        <div class='risk-row'>{risk_cells_html}</div>
        <table class='meta-table'>
          <tr><td>Recommended horizon</td><td>{horizon}</td></tr>
        </table>
      </div>
    </div>
  </div>

  <div class='section-label'>Investment Objective</div>
  <p class='objective'>{cfg['objective']}</p>

  <div class='two-col'>
    <div class='col'>
      <div class='section-label'>Market Commentary</div>
      <ul class='bullet-list'>{market_lis}</ul>
    </div>
    <div class='col'>
      <div class='section-label'>Management Commentary</div>
      <ul class='bullet-list'>{mgmt_lis}</ul>
    </div>
  </div>

  <div class='section-label'>Performance — {pf['name']} vs Benchmarks</div>
  <div class='chart-block'>
    <img src='{chart_img}' alt='Performance chart'/>
  </div>

  <table class='perf-table monthly-matrix'>
    <thead>
      <tr><th></th>
        <th>Jan</th><th>Feb</th><th>Mar</th><th>Apr</th><th>May</th><th>Jun</th>
        <th>Jul</th><th>Aug</th><th>Sep</th><th>Oct</th><th>Nov</th><th>Dec</th>
      </tr>
    </thead>
    <tbody>{perf_rows}</tbody>
  </table>
  <div style='font-size:7.5px; color:{TEXT_DIM}; margin-top:3px; text-align:right;'>
    Net monthly returns (%). Empty cells = period not yet completed since inception.
  </div>

  <div class='page-num'>1 / 2</div>
</div>


<div class='page'>
  <div class='top-band'>
    <span><b>{pf['name'].upper()}</b> &nbsp;|&nbsp; Monthly Report — {period_label}</span>
    <span>Paper portfolio. Not financial advice. Personal views only.</span>
  </div>

  <div class='section-label'>Allocation</div>
  <div class='alloc-grid'>
    <table class='alloc-table'>
      <caption>Layer</caption>
      <tbody>{alloc_layer}</tbody>
    </table>
    <table class='alloc-table'>
      <caption>Sector</caption>
      <tbody>{alloc_sector}</tbody>
    </table>
    <table class='alloc-table'>
      <caption>Geography</caption>
      <tbody>{alloc_geo}</tbody>
    </table>
  </div>

  <div class='section-label'>Top 10 Holdings</div>
  <table class='holdings-table'>
    <thead>
      <tr><th>Ticker</th><th>Name</th><th>Country</th><th>Sector</th><th class='r'>Weight</th></tr>
    </thead>
    <tbody>{holdings_rows}</tbody>
  </table>

  <div class='two-col' style='margin-top: 10px;'>
    <div class='col'>
      <div class='section-label'>Top 5 Contributors</div>
      <table class='contrib-table'>
        <thead>
          <tr><th>Ticker</th><th>Name</th><th class='r'>Weight</th><th class='r'>Contrib</th></tr>
        </thead>
        <tbody>{contrib_rows}</tbody>
      </table>
    </div>
    <div class='col'>
      <div class='section-label'>Top 5 Detractors</div>
      <table class='contrib-table'>
        <thead>
          <tr><th>Ticker</th><th>Name</th><th class='r'>Weight</th><th class='r'>Contrib</th></tr>
        </thead>
        <tbody>{detract_rows}</tbody>
      </table>
    </div>
  </div>

  <div class='section-label'>Risk Metrics</div>
  <div class='risk-metrics-grid'>
    <div class='metric-card'>
      <div class='label'>Max Drawdown</div>
      <div class='value'>{ctx['mdd']:+.2f}%</div>
      <div class='sub'>Since inception</div>
    </div>
    <div class='metric-card'>
      <div class='label'>Top 3 Concentration</div>
      <div class='value'>{ctx['top3_pct']:.1f}%</div>
      <div class='sub'>{ctx['top3_names']}</div>
    </div>
    <div class='metric-card'>
      <div class='label'>Volatility (ann.)</div>
      <div class='value'>—</div>
      <div class='sub'>Available after 60 trading days</div>
    </div>
    <div class='metric-card'>
      <div class='label'>Sharpe / Beta</div>
      <div class='value'>—</div>
      <div class='sub'>Available after 60 trading days</div>
    </div>
  </div>

  <div class='footer'>
    <strong>Disclaimer:</strong> {pf['name']} is a paper portfolio for educational and demonstrative
    purposes only. It does not constitute financial advice, an investment recommendation, or a solicitation
    to buy or sell any security or digital asset. Performance shown is simulated and net of zero fees
    (paper portfolio). Past performance, simulated or real, is not indicative of future results. The author
    is not a registered investment advisor. All readers should conduct their own due diligence.
  </div>

  <div class='page-num'>2 / 2</div>
</div>

</body>
</html>"""
    return html


# ── Main ──────────────────────────────────────────────────────────────────────
def generate(portfolio_id: str):
    if portfolio_id not in CONFIGS:
        raise ValueError(f"Unknown portfolio: {portfolio_id}. Use one of: {list(CONFIGS.keys())}")
    cfg = CONFIGS[portfolio_id]
    print(f"\n{'=' * 60}\nGenerating monthly report for: {portfolio_id}\n{'=' * 60}")

    portfolio = fetch_portfolio(portfolio_id)
    positions = fetch_positions(portfolio_id)
    inception = str(portfolio["inception_date"])
    end = str(pd.Timestamp(cfg["report_date"]) + pd.Timedelta(days=1))[:10]

    print(f"  Portfolio: {portfolio['name']}")
    print(f"  Positions: {len(positions)}")
    print(f"  Period:    {inception} → {cfg['report_date']}")

    bench_pri = portfolio.get("benchmark_primary")
    bench_pri_lbl = portfolio.get("benchmark_primary_label") or bench_pri or ""
    bench_sec = portfolio.get("benchmark_secondary")
    bench_sec_lbl = portfolio.get("benchmark_secondary_label") or bench_sec or ""
    benchmarks_for_history = tuple(b for b in [bench_pri, bench_sec] if b)

    tickers = tuple(p["ticker"] for p in positions)
    print("\n  Fetching live prices...")
    prices = fetch_live_prices(tickers)

    print("  Fetching history...")
    history = fetch_history(tickers, inception, end, benchmarks_for_history)
    if history.empty:
        print("  ERROR: history empty")
        return

    print("  Computing metrics...")
    positions, cash_pct = compute_position_metrics(positions, prices)
    port_index = build_index(history, positions)
    if port_index.empty:
        print("  ERROR: portfolio index empty")
        return

    positions_w = sorted(positions, key=lambda p: p["current_weight"] or 0, reverse=True)
    top10 = positions_w[:10]
    valid_contrib = [p for p in positions if p.get("contribution") is not None]
    sorted_contrib = sorted(valid_contrib, key=lambda p: p["contribution"], reverse=True)
    top5_contrib = sorted_contrib[:5]
    bottom5_contrib = sorted(valid_contrib, key=lambda p: p["contribution"])[:5]

    alloc_layer  = aggregate_alloc(positions, "layer", cash_pct)
    alloc_sector = aggregate_alloc(positions, "sector", cash_pct)
    alloc_geo    = aggregate_alloc(positions, "geography", cash_pct)

    mdd = max_drawdown(port_index) or 0
    top3 = positions_w[:3]
    top3_pct = sum(p["current_weight"] for p in top3)
    top3_names = " · ".join(p["ticker"] for p in top3)

    # Monthly returns matrix
    inception_dt = pd.Timestamp(inception)
    report_dt    = pd.Timestamp(cfg["report_date"])
    monthly_returns = {report_dt.year: {m: None for m in range(1, 13)}}
    monthly = port_index.resample("ME").last()
    for ts, val in monthly.items():
        first_of_month = ts.replace(day=1)
        if inception_dt <= first_of_month and ts <= report_dt:
            prev_ts = ts - pd.offsets.MonthEnd(1)
            prev_val = monthly.get(prev_ts)
            if prev_val is None or pd.isna(prev_val):
                prev_val = 100.0
            ret = round(float((val / prev_val - 1) * 100), 2)
            monthly_returns.setdefault(ts.year, {m: None for m in range(1, 13)})
            monthly_returns[ts.year][ts.month] = ret

    print("  Generating chart...")
    accent = portfolio.get("color_primary") or "#A78BFA"
    benchmark_lines = []
    if bench_sec and bench_sec in history.columns:
        benchmark_lines.append((bench_sec, bench_sec_lbl, ":"))
    if bench_pri and bench_pri in history.columns:
        benchmark_lines.append((bench_pri, bench_pri_lbl, "--"))
    chart_b64 = generate_chart_b64(history, port_index, portfolio["name"], benchmark_lines, accent)

    ctx = {
        "portfolio_id":      portfolio_id,
        "portfolio":         portfolio,
        "config":            cfg,
        "positions":         positions,
        "n_positions":       len(positions),
        "cash_pct":          cash_pct,
        "alloc_layer":       alloc_layer,
        "alloc_sector":      alloc_sector,
        "alloc_geo":         alloc_geo,
        "top10":             top10,
        "top5_contrib":      top5_contrib,
        "bottom5_contrib":   bottom5_contrib,
        "mdd":               mdd,
        "top3_pct":          top3_pct,
        "top3_names":        top3_names,
        "chart_b64":         chart_b64,
        "monthly_returns":   monthly_returns,
    }

    print("  Rendering HTML...")
    html = render_html(ctx)

    output_dir = PROJECT_ROOT / cfg["subfolder"] / "reports"
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{cfg['subfolder'].replace(' ', '')}_Monthly_{cfg['report_date']}.html"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\n[OK] Saved: {out_path.absolute()}")


def main():
    portfolio_id = sys.argv[1] if len(sys.argv) > 1 else "visionnaire"
    generate(portfolio_id)


if __name__ == "__main__":
    main()
