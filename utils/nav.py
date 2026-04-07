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
        background: rgba(8, 11, 20, 0.97);
        backdrop-filter: blur(10px);
        border-bottom: 1px solid {BORDER};
        padding: 0 2rem;
        height: 44px;
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }}
    .nav-logo {{
        font-size: 0.82rem;
        font-weight: 800;
        color: #EEF0F6;
        letter-spacing: -0.2px;
        margin-right: 1.5rem;
        text-decoration: none;
    }}
    .nav-link {{
        font-size: 0.8rem;
        font-weight: 500;
        color: #4A5568;
        text-decoration: none;
        padding: 0.25rem 0.75rem;
        border-radius: 6px;
        transition: color 0.15s;
    }}
    .nav-link:hover {{
        color: #EEF0F6;
        background: {BORDER};
    }}
    .nav-active {{
        color: {NAV_ACTIVE_COLOR} !important;
        background: {NAV_ACTIVE_BG} !important;
    }}
    .block-container {{ padding-top: 4rem !important; }}
</style>
<div class="nav-bar">
    <a href="/" target="_self" class="nav-logo">Le Visionnaire</a>
    {links_html}
</div>
""", unsafe_allow_html=True)
