# ── Visual identity for Le Visionnaire ───────────────────────────────────────
# To revert to legacy theme, swap the values below with the LEGACY palette
# stored in memory/project_visionnaire_theme.md

# Backgrounds
BG          = "#080B14"
BG_CARD     = "#0F1320"
GRID        = "#161D2E"
BORDER      = "#1E2840"

# Typography
TEXT_BRIGHT = "#EEF0F6"
TEXT_MID    = "#9AA3B8"
TEXT_DIM    = "#4A5568"

# Accent & actions
ACCENT      = "#818CF8"    # indigo — primary, nav active, CTA
POSITIVE    = "#34D399"    # emerald green
NEGATIVE    = "#F87171"    # soft red
SWITCH      = "#60A5FA"    # sky blue
TRIM        = "#FBBF24"    # amber

# Chart-specific
PORTFOLIO_LINE  = ACCENT
BENCHMARK_LINE  = "#3A4560"
HLINE_COLOR     = "#252D40"

# Nav
NAV_ACTIVE_COLOR = ACCENT
NAV_ACTIVE_BG    = "rgba(129, 140, 248, 0.10)"

# Stacked area palette (positions)
POSITION_COLORS = [
    "#818CF8",   # indigo
    "#34D399",   # emerald
    "#60A5FA",   # sky
    "#FBBF24",   # amber
    "#F472B6",   # pink
    "#A78BFA",   # violet
    "#2DD4BF",   # teal
    "#FB923C",   # orange
    "#94A3B8",   # slate
    "#E879F9",   # fuchsia
    "#4ADE80",   # green
]

CASH_COLOR  = "#1A2235"


def action_colors():
    return {
        "IN":     POSITIVE,
        "OUT":    NEGATIVE,
        "SWITCH": SWITCH,
        "TRIM":   TRIM,
    }


def chart_layout(height=400):
    """Base Plotly layout for all charts."""
    return dict(
        plot_bgcolor=BG,
        paper_bgcolor=BG,
        font=dict(color=TEXT_MID, size=11),
        legend=dict(
            orientation="h",
            yanchor="bottom", y=1.02,
            xanchor="right", x=1,
            font=dict(size=10),
            bgcolor="rgba(0,0,0,0)",
        ),
        yaxis=dict(gridcolor=GRID, zeroline=False),
        xaxis=dict(gridcolor=GRID),
        hovermode="closest",
        height=height,
        margin=dict(l=0, r=0, t=30, b=0),
    )
