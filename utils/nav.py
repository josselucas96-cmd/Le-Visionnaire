import streamlit as st
from utils.theme import NAV_ACTIVE_COLOR, NAV_ACTIVE_BG, BG, BORDER


def render_nav(current: str):
    """
    Renders a top navigation bar.
    current: one of 'app', 'history', 'research', 'about'
    """
    pages = [
        ("Portfolio",     "/",                "app"),
        ("History",       "/HistoryAnalysis", "history"),
        ("Stock Papers",  "/Research",        "research"),
        ("About",         "/About",           "about"),
    ]

    links_html = ""
    for label, href, key in pages:
        active = "nav-active" if key == current else ""
        links_html += f'<a href="{href}" target="_self" class="nav-link {active}">{label}</a>'

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
        .block-container {{ padding-top: 6.5rem !important; }}
    }}
</style>
<div class="nav-bar">
    <a href="/" target="_self" class="nav-logo">Le Visionnaire</a>
    <div class="nav-links">{links_html}</div>
</div>
""", unsafe_allow_html=True)
