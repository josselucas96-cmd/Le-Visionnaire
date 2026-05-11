import streamlit as st
from utils import SPECULA_ICON
from utils.portfolio import render_portfolio_page

st.set_page_config(
    page_title="Le Nakamoto",
    page_icon=SPECULA_ICON,
    layout="wide",
    initial_sidebar_state="collapsed",
)

render_portfolio_page("nakamoto", options={
    # Single-thesis portfolio (Bitcoin Treasury Equities) — sector /
    # thematic donuts add little signal. Only the geographic spread
    # is genuinely informative, so render that donut alone.
    "show_donuts": ["Geography"],
    "show_risk_analysis": True,
})
