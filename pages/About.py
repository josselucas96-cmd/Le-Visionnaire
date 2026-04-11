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
st.markdown('<div class="about-title">Hello ! I\'m Lucas</div>', unsafe_allow_html=True)

st.markdown("""
<div class="about-body">

<p>
My journey began with… <strong>anthropology</strong>. Studying the nature of money in primitive societies
(shellfish used as currency?) naturally led me to follow the rise of <strong>cryptocurrencies</strong>
(is this Bitcoin-thing for real?), then into traditional finance (Options can actually skew risk/reward?).
After three years in Wealth Management Advisory in Geneva, I want to
<strong>share my insights and convictions</strong> with anyone who might find them valuable.
</p>

<div class="section-title">On this website, you will find:</div>
<p>
<strong>Portfolio Management:</strong> simulated portfolios, each built around a defined strategy and
risk profile, tracked in real time.<br><br>
<strong>Equity Research:</strong> investment theses on the positions I hold and the ideas I find worth examining.<br><br>
<strong>Articles:</strong> Personal thoughts on analytical frameworks, portfolio &amp; risk management,
the macro and geopolitical environment, and stock selection.
</p>

<div class="section-title">Why go public?</div>
<p>
A conviction held in private is easy. My goal is to demonstrate the validity of a global strategy
over a 5-year horizon. If the thesis is correct, the numbers will show it. If it is wrong, it will
be fully visible and documented in the <strong>Mistake Log</strong>. Being honest about errors is the
most effective way to actually improve.
</p>

<div class="section-title">A Note on the Project</div>
<p>
This is a paper portfolio. No real money is at stake. What is real: the analysis, the decisions,
the timestamps, and the accountability. Nothing here is financial advice. These are my personal
views, documented publicly.
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
