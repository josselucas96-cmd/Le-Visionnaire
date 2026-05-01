import streamlit as st
from utils.theme import NAV_ACTIVE_COLOR, NAV_ACTIVE_BG, BG, BORDER


def render_nav(current: str):
    """
    Renders the top navigation bar.
    current: one of 'specula', 'visionnaire', 'nakamoto', 'history', 'research', 'about'

    Portfolio button is a dropdown with Le Visionnaire + Le Nakamoto.
    All links use target="_top" to force a real URL update (bypasses Streamlit's
    in-app link interception that was leaving the URL stale).
    """
    portfolio_keys = {"visionnaire", "nakamoto"}
    is_portfolio_active = current in portfolio_keys
    v_active = "dropdown-active" if current == "visionnaire" else ""
    n_active = "dropdown-active" if current == "nakamoto" else ""

    # Build the dropdown menu HTML on a single line (avoids Markdown code-block trap)
    portfolio_dropdown_html = (
        '<div class="dropdown-menu">'
        f'<a href="/Visionnaire" target="_top" class="dropdown-item {v_active}">'
        '<span class="dropdown-portfolio-name">Le Visionnaire</span>'
        '<span class="dropdown-portfolio-tag">High-Conviction Equity</span>'
        '</a>'
        f'<a href="/Nakamoto" target="_top" class="dropdown-item {n_active}">'
        '<span class="dropdown-portfolio-name">Le Nakamoto</span>'
        '<span class="dropdown-portfolio-tag">Digital Asset Treasuries</span>'
        '</a>'
        '</div>'
    )

    portfolio_active = "nav-active" if is_portfolio_active else ""
    portfolio_html = (
        '<div class="nav-dropdown">'
        f'<span class="nav-link nav-link-dropdown {portfolio_active}">Portfolio <span class="caret">▾</span></span>'
        f'{portfolio_dropdown_html}'
        '</div>'
    )

    # Single-link entries before and after the Portfolio dropdown
    simple_pages = [
        ("Accueil",      "/",                "specula"),
        ("History",      "/HistoryAnalysis", "history"),
        ("Stock Papers", "/Research",        "research"),
        ("About",        "/About",           "about"),
    ]
    accueil_label, accueil_href, accueil_key = simple_pages[0]
    accueil_active = "nav-active" if accueil_key == current else ""
    accueil_html = f'<a href="{accueil_href}" target="_top" class="nav-link {accueil_active}">{accueil_label}</a>'

    other_links_html = ""
    for label, href, key in simple_pages[1:]:
        active = "nav-active" if key == current else ""
        other_links_html += f'<a href="{href}" target="_top" class="nav-link {active}">{label}</a>'

    links_html = accueil_html + portfolio_html + other_links_html

    st.markdown(f"""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@600;700&display=swap');

    /* Global font override — exclude span to preserve expander glyphs */
    html, body, p, div, td, th, label,
    .stMarkdown, .stDataFrame, .stMetric,
    [data-testid="stExpander"] summary p,
    [data-testid="stExpander"] > div {{
        font-family: "Avenir Next LT Pro", "Avenir Next", "Avenir", "Nunito", sans-serif !important;
    }}

    [data-testid="stHeader"] {{ display: none !important; }}

    .nav-bar {{
        position: fixed;
        top: 0; left: 0; right: 0;
        z-index: 999999;
        background: rgba(6, 9, 18, 0.97);
        backdrop-filter: blur(14px);
        border-bottom: 1px solid rgba(255,255,255,0.07);
        padding: 0 2.5rem;
        height: 52px;
        display: flex;
        align-items: center;
    }}
    .nav-logo {{
        font-family: 'Cormorant Garamond', Georgia, serif !important;
        font-size: 1.25rem !important;
        font-weight: 700 !important;
        color: #00D09C !important;
        letter-spacing: 0.5px !important;
        text-decoration: none !important;
        flex-shrink: 0;
        margin-right: auto;
    }}
    .nav-links {{
        display: flex;
        align-items: center;
        gap: 0.25rem;
        position: absolute;
        left: 50%;
        transform: translateX(-50%);
    }}
    .nav-link {{
        font-family: "Avenir Next LT Pro", "Avenir Next", "Avenir", sans-serif !important;
        font-size: 0.82rem !important;
        font-weight: 500 !important;
        color: #EEF0F6 !important;
        text-decoration: none !important;
        padding: 0.3rem 1rem;
        height: 52px;
        display: inline-flex;
        align-items: center;
        border-bottom: 2px solid transparent;
        transition: color 0.15s, border-color 0.15s;
        letter-spacing: 0.2px;
        cursor: pointer;
    }}
    .nav-link:hover {{
        color: #ffffff !important;
        border-bottom-color: rgba(255,255,255,0.2);
    }}
    .nav-active {{
        color: #ffffff !important;
        border-bottom-color: #00D09C !important;
        font-weight: 600 !important;
    }}
    .nav-link-dropdown .caret {{
        font-size: 0.7rem;
        margin-left: 0.3rem;
        opacity: 0.7;
    }}

    /* ── Dropdown ── */
    .nav-dropdown {{
        position: relative;
        height: 52px;
        display: flex;
        align-items: center;
    }}
    .dropdown-menu {{
        display: none;
        position: absolute;
        top: 100%;
        left: 50%;
        transform: translateX(-50%);
        min-width: 240px;
        background: rgba(6, 9, 18, 0.98);
        backdrop-filter: blur(14px);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 8px;
        padding: 0.5rem;
        margin-top: 0;
        box-shadow: 0 10px 30px rgba(0,0,0,0.5);
    }}
    .nav-dropdown:hover .dropdown-menu {{
        display: block;
    }}
    .dropdown-item {{
        display: flex;
        flex-direction: column;
        padding: 0.6rem 0.9rem;
        text-decoration: none !important;
        border-radius: 6px;
        transition: background 0.15s;
    }}
    .dropdown-item:hover {{
        background: rgba(255,255,255,0.05);
    }}
    .dropdown-active {{
        background: rgba(0, 208, 156, 0.08);
    }}
    .dropdown-portfolio-name {{
        font-family: 'Cormorant Garamond', Georgia, serif !important;
        font-size: 1.05rem !important;
        font-weight: 700 !important;
        color: #F9FAFB !important;
        line-height: 1.2;
    }}
    .dropdown-portfolio-tag {{
        font-size: 0.68rem;
        color: #6B7280;
        margin-top: 0.15rem;
        letter-spacing: 0.3px;
    }}

    .block-container {{ padding-top: 4.2rem !important; }}

    /* ── Mobile nav: stack logo above links ── */
    @media (max-width: 768px) {{
        .nav-bar {{
            height: auto;
            flex-direction: column;
            align-items: flex-start;
            padding: 0.65rem 1.2rem 0 1.2rem;
        }}
        .nav-logo {{
            margin-right: 0;
            margin-bottom: 0.1rem;
        }}
        .nav-links {{
            position: static;
            transform: none;
            left: auto;
            width: 100%;
            overflow-x: auto;
            flex-wrap: nowrap;
            justify-content: flex-start;
            gap: 0;
            scrollbar-width: none;
        }}
        .nav-links::-webkit-scrollbar {{ display: none; }}
        .nav-link {{
            height: 36px;
            padding: 0 0.8rem;
            font-size: 0.78rem !important;
            border-bottom-width: 2px;
            flex-shrink: 0;
        }}
        .nav-dropdown {{ height: 36px; }}
        .dropdown-menu {{
            min-width: 200px;
            left: 0;
            transform: none;
        }}
        .block-container {{ padding-top: 6.5rem !important; }}
    }}
</style>
<div class="nav-bar">
    <a href="/" target="_top" class="nav-logo">Specula</a>
    <div class="nav-links">{links_html}</div>
</div>
""", unsafe_allow_html=True)
