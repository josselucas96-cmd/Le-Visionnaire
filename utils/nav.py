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
        background: rgba(8, 11, 20, 0.98);
        backdrop-filter: blur(12px);
        border-bottom: 1px solid {BORDER};
        padding: 0 2.5rem;
        height: 50px;
        display: flex;
        align-items: center;
        gap: 0.25rem;
    }}
    .nav-logo {{
        font-size: 0.95rem;
        font-weight: 900;
        color: #EEF0F6;
        letter-spacing: -0.5px;
        margin-right: 2rem;
        text-decoration: none;
        flex-shrink: 0;
    }}
    .nav-link {{
        font-size: 0.82rem;
        font-weight: 600;
        color: #7A8599;
        text-decoration: none;
        padding: 0.35rem 0.9rem;
        border-radius: 6px;
        transition: color 0.15s, background 0.15s;
        letter-spacing: 0.1px;
    }}
    .nav-link:hover {{
        color: #EEF0F6;
        background: rgba(255,255,255,0.06);
    }}
    .nav-active {{
        color: #EEF0F6 !important;
        background: {NAV_ACTIVE_BG} !important;
        border: 1px solid rgba(129,140,248,0.25);
    }}
    .block-container {{ padding-top: 4.2rem !important; }}
</style>
<div class="nav-bar">
    <a href="/" target="_self" class="nav-logo">Le Visionnaire</a>
    {links_html}
</div>
""", unsafe_allow_html=True)
