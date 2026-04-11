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
    [data-testid="stHeader"] {{ display: none !important; }}

    .nav-bar {{
        position: fixed;
        top: 0; left: 0; right: 0;
        z-index: 999999;
        background: rgba(6, 9, 18, 0.97);
        backdrop-filter: blur(14px);
        border-bottom: 1px solid rgba(255,255,255,0.06);
        padding: 0 2.5rem;
        height: 52px;
        display: flex;
        align-items: center;
        gap: 0;
    }}
    .nav-logo {{
        font-size: 0.9rem;
        font-weight: 900;
        color: #EEF0F6;
        letter-spacing: 0.5px;
        text-transform: uppercase;
        text-decoration: none;
        flex-shrink: 0;
        padding-right: 2rem;
        margin-right: 1.5rem;
        border-right: 1px solid rgba(255,255,255,0.1);
    }}
    .nav-link {{
        font-size: 0.8rem;
        font-weight: 500;
        color: #5A6478;
        text-decoration: none;
        padding: 0 1rem;
        height: 52px;
        display: inline-flex;
        align-items: center;
        border-bottom: 2px solid transparent;
        transition: color 0.15s, border-color 0.15s;
        letter-spacing: 0.2px;
    }}
    .nav-link:hover {{
        color: #CBD5E1;
        border-bottom-color: rgba(255,255,255,0.15);
    }}
    .nav-active {{
        color: #EEF0F6 !important;
        border-bottom-color: {NAV_ACTIVE_COLOR} !important;
        font-weight: 600 !important;
    }}
    .block-container {{ padding-top: 4.2rem !important; }}
</style>
<div class="nav-bar">
    <a href="/" target="_self" class="nav-logo">Le Visionnaire</a>
    {links_html}
</div>
""", unsafe_allow_html=True)
