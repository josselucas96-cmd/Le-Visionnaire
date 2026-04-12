import html
import streamlit as st
from utils.research import get_research
from utils.nav import render_nav

st.set_page_config(
    page_title="Stock Papers | Le Visionnaire",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
    [data-testid="stSidebar"] { display: none; }
    .block-container { padding-top: 3.5rem; padding-bottom: 2rem; }

    .research-hero {
        background: linear-gradient(135deg, #0D1F2D 0%, #0E1117 60%);
        border: 1px solid #1C2E3D;
        border-radius: 14px;
        padding: 2.8rem 3rem;
        margin-bottom: 2.5rem;
        position: relative;
        overflow: hidden;
    }
    .research-hero::before {
        content: "";
        position: absolute;
        top: -60px; right: -60px;
        width: 280px; height: 280px;
        background: radial-gradient(circle, rgba(0,208,156,0.08) 0%, transparent 70%);
        border-radius: 50%;
    }
    .hero-label {
        font-size: 0.72rem; font-weight: 700; letter-spacing: 2px;
        color: #00D09C; text-transform: uppercase; margin-bottom: 0.6rem;
    }
    .hero-title {
        font-size: 2.4rem; font-weight: 800; letter-spacing: -1px;
        line-height: 1.15; margin-bottom: 0.8rem;
    }
    .hero-sub {
        font-size: 0.95rem; color: #888; max-width: 520px; line-height: 1.7;
    }

    .paper-card {
        background: #13181F;
        border: 1px solid #1E2530;
        border-radius: 12px;
        padding: 1.6rem 1.8rem;
        margin-bottom: 1.1rem;
        position: relative;
        overflow: hidden;
        transition: border-color 0.2s, background 0.2s;
    }
    .paper-card:hover { border-color: #2A3A4A; background: #161D26; }
    .paper-card-locked {
        background: #111418;
        border: 1px solid #1A1F26;
        opacity: 0.75;
    }
    .paper-accent {
        position: absolute;
        left: 0; top: 0; bottom: 0;
        width: 3px;
        background: linear-gradient(180deg, #00D09C, #0097B2);
        border-radius: 3px 0 0 3px;
    }
    .paper-accent-locked {
        background: #2A2A2A;
    }
    .paper-ticker {
        font-size: 0.7rem; font-weight: 800; letter-spacing: 1.5px;
        color: #00D09C; text-transform: uppercase; margin-bottom: 0.4rem;
    }
    .paper-title {
        font-size: 1.1rem; font-weight: 700; margin-bottom: 0.5rem; line-height: 1.35;
    }
    .paper-summary {
        font-size: 0.86rem; color: #7A8595; line-height: 1.65; margin-bottom: 0.9rem;
    }
    .paper-meta {
        font-size: 0.72rem; color: #3A4555; letter-spacing: 0.3px;
    }
    .locked-tag {
        display: inline-flex; align-items: center; gap: 5px;
        font-size: 0.7rem; color: #555; background: #1A1F26;
        border: 1px solid #252B35; border-radius: 20px;
        padding: 3px 10px; margin-bottom: 1rem;
    }
    .section-divider {
        border: none; border-top: 1px solid #1A1F26; margin: 2rem 0;
    }
    .disclaimer {
        font-size: 0.72rem; color: #333; margin-top: 3rem;
        border-top: 1px solid #1A1F26; padding-top: 1rem; line-height: 1.5;
    }
    /* Link button — orange BTC */
    [data-testid="stLinkButton"] button {
        background-color: #F7931A !important;
        border: 1px solid #F7931A !important;
        color: #0D1117 !important;
        font-weight: 700 !important;
    }
    [data-testid="stLinkButton"] button:hover {
        background-color: #E0820F !important;
        border-color: #E0820F !important;
        color: #0D1117 !important;
    }
</style>
""", unsafe_allow_html=True)

render_nav("research")

# ── Hero ──────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="research-hero">
    <div class="hero-label">Le Visionnaire · Research</div>
    <div class="hero-title">Stock Papers</div>
    <div class="hero-sub">
        In-depth equity analysis on portfolio positions and market themes.
    </div>
</div>
""", unsafe_allow_html=True)

st.write("")

# ── Papers ────────────────────────────────────────────────────────────────────
papers = [p for p in get_research() if p["status"] in ("published", "locked") and p.get("doc_type", "Stock Paper") == "Stock Paper"]

if not papers:
    st.markdown(
        "<div style='color:#444; font-size:0.9rem; padding: 2rem 0;'>"
        "No papers published yet — check back soon.</div>",
        unsafe_allow_html=True,
    )
    st.stop()

for p in papers:
    is_locked = p["status"] == "locked"
    card_class = "paper-card paper-card-locked" if is_locked else "paper-card"
    accent_class = "paper-accent paper-accent-locked" if is_locked else "paper-accent"

    ticker_html  = f'<div class="paper-ticker">{html.escape(p["ticker"])}</div>' if p.get("ticker") else ""
    date_html    = f'<div class="paper-meta">{html.escape(str(p.get("published_at", "")))}</div>' if p.get("published_at") else ""
    summary_html = f'<div class="paper-summary">{html.escape(str(p.get("summary", "")))}</div>' if p.get("summary") else ""
    title_html   = html.escape(str(p.get("title", "")))

    locked_html = """
        <div class="locked-tag">🔒 &nbsp;Full access restricted</div>
    """ if is_locked else ""

    st.markdown(f"""
    <div class="{card_class}">
        <div class="{accent_class}"></div>
        {ticker_html}
        <div class="paper-title">{title_html}</div>
        {summary_html}
        {locked_html}
        {date_html}
    </div>
    """, unsafe_allow_html=True)

    if not is_locked and p.get("file_url"):
        st.link_button("Read the full paper →", p["file_url"])
        st.write("")

# ── Disclaimer ────────────────────────────────────────────────────────────────
st.markdown("""
<div class="disclaimer">
These papers are published for informational and educational purposes only
and do not constitute financial or investment advice.
</div>
""", unsafe_allow_html=True)
