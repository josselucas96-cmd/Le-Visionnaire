import streamlit as st
from utils.portfolio import render_portfolio_page

st.set_page_config(
    page_title="Le Nakamoto",
    page_icon="₿",
    layout="wide",
    initial_sidebar_state="collapsed",
)

render_portfolio_page("nakamoto", options={
    "show_donuts": ["Geography"],
    "show_risk_analysis": False,
    "show_research_teaser": False,
    "show_documents_section": False,
})
