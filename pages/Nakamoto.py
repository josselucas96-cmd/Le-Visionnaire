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
    # Layer donut shows the IPS-aligned split: Anchor (structural core)
    # vs Exploratory (smaller-cap amplification) vs Income (BTC-backed
    # preferreds overlay).
    "show_donuts": ["Layer", "Sector", "Thematic", "Geography"],
    "show_risk_analysis": True,
})
