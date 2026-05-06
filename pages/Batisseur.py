import streamlit as st
from utils.portfolio import render_portfolio_page

st.set_page_config(
    page_title="Le Bâtisseur",
    page_icon="⚒",
    layout="wide",
    initial_sidebar_state="collapsed",
)

render_portfolio_page("batisseur", options={
    # Layer (Obvious / Haute Qualité / Diversification / Tactical) is internal
    # taxonomy — keep it in DB for monitoring but hide from public display.
    "show_layer_column": False,
    "show_donuts": ["Sector", "Thematic", "Geography"],
})
