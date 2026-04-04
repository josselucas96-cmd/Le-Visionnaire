import streamlit as st
from utils.nav import render_nav

st.set_page_config(
    page_title="About | Le Visionnaire",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
    [data-testid="stSidebar"] { display: none; }
    .block-container { padding-top: 3.5rem; padding-bottom: 2rem; max-width: 760px; }
    .about-label {
        font-size: 0.7rem; font-weight: 700; letter-spacing: 2px;
        color: #00D09C; text-transform: uppercase; margin-bottom: 0.6rem;
    }
    .about-title {
        font-size: 2.2rem; font-weight: 800; letter-spacing: -0.5px;
        margin-bottom: 1.8rem; line-height: 1.2;
    }
    .about-body {
        font-size: 0.95rem; color: #CCC; line-height: 1.85;
    }
    .about-body p { margin-bottom: 1.2rem; }
    .section-title {
        font-size: 1.1rem; font-weight: 700; margin-top: 2rem; margin-bottom: 0.6rem;
        color: #EEE;
    }
    .disclaimer {
        font-size: 0.72rem; color: #444; margin-top: 3rem;
        border-top: 1px solid #1A1F26; padding-top: 1rem; line-height: 1.5;
    }
</style>
""", unsafe_allow_html=True)

render_nav("about")
st.write("")

st.markdown('<div class="about-label">Le Visionnaire</div>', unsafe_allow_html=True)
st.markdown('<div class="about-title">About this portfolio</div>', unsafe_allow_html=True)

st.markdown("""
<div class="about-body">

<div class="section-title">Who I am</div>
<p>
Independent investor and trader, focused on high-conviction equity positions at the intersection
of technology, healthcare innovation, and emerging asset classes.
This portfolio is a public, fully transparent paper trading simulation — every position,
every move, and every result is visible in real time.
</p>

<div class="section-title">Investment philosophy</div>
<p>
I invest in companies I believe are building something durable — businesses with asymmetric
upside, strong product-market fit, and a structural advantage that compounds over time.
I favour concentrated positions over diversification for the sake of it.
If I'm not willing to hold through a 40% drawdown, I won't take the position.
</p>

<div class="section-title">Why publish it publicly?</div>
<p>
Accountability sharpens thinking. Publishing forces discipline — it's easy to have conviction
in private. Doing it in public, with the numbers visible, is a different standard entirely.
The goal is to build a real track record, not a curated one.
</p>

<div class="section-title">About the research</div>
<p>
The Stock Papers published here are independent analyses written for my own process first.
They cover the equity positions in this portfolio and occasionally broader market themes.
Nothing here is financial advice — these are my own views, documented publicly.
</p>

</div>
""", unsafe_allow_html=True)

st.markdown("""
<div class="disclaimer">
This portfolio is a paper trading simulation and does not involve real financial assets.
Nothing published here constitutes financial, investment, or legal advice.
I am not a registered financial advisor.
</div>
""", unsafe_allow_html=True)
