import streamlit as st


def render_nav(current: str):
    """
    Renders a top navigation bar.
    current: one of 'app', 'research', 'about'
    """
    pages = [
        ("Portfolio",     "/",         "app"),
        ("Stock Papers",  "/Research", "research"),
        ("About",         "/About",    "about"),
    ]

    links_html = ""
    for label, href, key in pages:
        active = "nav-active" if key == current else ""
        links_html += f'<a href="{href}" target="_self" class="nav-link {active}">{label}</a>'

    st.markdown(f"""
<style>
    /* Hide Streamlit's own header bar */
    [data-testid="stHeader"] {{ display: none !important; }}

    .nav-bar {{
        position: fixed;
        top: 0; left: 0; right: 0;
        z-index: 999999;
        background: rgba(14, 17, 23, 0.97);
        backdrop-filter: blur(8px);
        border-bottom: 1px solid #1E2530;
        padding: 0 2rem;
        height: 44px;
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }}
    .nav-logo {{
        font-size: 0.82rem;
        font-weight: 800;
        color: #EEE;
        letter-spacing: -0.2px;
        margin-right: 1.5rem;
        text-decoration: none;
    }}
    .nav-link {{
        font-size: 0.8rem;
        font-weight: 500;
        color: #888;
        text-decoration: none;
        padding: 0.25rem 0.75rem;
        border-radius: 6px;
    }}
    .nav-link:hover {{
        color: #EEE;
        background: #1E2530;
    }}
    .nav-active {{
        color: #00D09C !important;
        background: rgba(0, 208, 156, 0.08) !important;
    }}
    .block-container {{ padding-top: 4rem !important; }}
</style>
<div class="nav-bar">
    <a href="/app" target="_self" class="nav-logo">Le Visionnaire</a>
    {links_html}
</div>
""", unsafe_allow_html=True)
