import streamlit as st
from utils.portfolio import render_portfolio_page

st.set_page_config(
    page_title="Le Visionnaire",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

render_portfolio_page("visionnaire")
