import streamlit as st
from utils import SPECULA_ICON
from utils.portfolio import render_portfolio_page

st.set_page_config(
    page_title="Le Visionnaire",
    page_icon=SPECULA_ICON,
    layout="wide",
    initial_sidebar_state="collapsed",
)

render_portfolio_page("visionnaire")
