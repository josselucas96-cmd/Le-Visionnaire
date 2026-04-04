import streamlit as st
from utils.research import get_research

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
    .paper-card {
        background: #161B22;
        border: 1px solid #21262D;
        border-radius: 10px;
        padding: 1.4rem 1.6rem;
        margin-bottom: 1.2rem;
        transition: border-color 0.2s;
    }
    .paper-card:hover { border-color: #444; }
    .paper-ticker {
        font-size: 0.75rem; font-weight: 700; letter-spacing: 1px;
        color: #00D09C; margin-bottom: 0.3rem;
    }
    .paper-title {
        font-size: 1.15rem; font-weight: 700; margin-bottom: 0.5rem;
    }
    .paper-summary {
        font-size: 0.88rem; color: #AAA; line-height: 1.6; margin-bottom: 1rem;
    }
    .paper-meta {
        font-size: 0.75rem; color: #555;
    }
    .locked-badge {
        display: inline-block; font-size: 0.72rem; color: #888;
        border: 1px solid #333; border-radius: 4px;
        padding: 2px 8px; margin-left: 8px; vertical-align: middle;
    }
</style>
""", unsafe_allow_html=True)

st.markdown('<p style="font-size:1.9rem; font-weight:800; letter-spacing:-0.5px; margin-bottom:0;">Stock Papers</p>', unsafe_allow_html=True)
st.caption("In-depth analysis on equity positions and market themes.")
st.write("")

papers = [p for p in get_research() if p["status"] in ("published", "locked")]

if not papers:
    st.info("No papers published yet. Check back soon.")
    st.stop()

for p in papers:
    ticker_tag = f'<div class="paper-ticker">{p["ticker"]}</div>' if p.get("ticker") else ""
    lock_badge = '<span class="locked-badge">🔒 Access restricted</span>' if p["status"] == "locked" else ""
    date_str = p.get("published_at") or ""

    st.markdown(f"""
    <div class="paper-card">
        {ticker_tag}
        <div class="paper-title">{p["title"]}{lock_badge}</div>
        <div class="paper-summary">{p.get("summary") or ""}</div>
        <div class="paper-meta">{date_str}</div>
    </div>
    """, unsafe_allow_html=True)

    if p["status"] == "published" and p.get("file_url"):
        st.link_button("Read PDF →", p["file_url"])

st.markdown("""
<div style="font-size:0.72rem; color:#444; margin-top:3rem; border-top:1px solid #222;
padding-top:1rem; line-height:1.5;">
These papers are published for informational purposes only and do not constitute
financial or investment advice.
</div>
""", unsafe_allow_html=True)
