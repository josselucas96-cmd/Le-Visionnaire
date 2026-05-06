import streamlit as st
from utils.portfolio import render_portfolio_page

st.set_page_config(
    page_title="Le Bâtisseur",
    page_icon="⚒",
    layout="wide",
    initial_sidebar_state="collapsed",
)

render_portfolio_page("batisseur", options={
    # Internal Layer taxonomy (Obvious / Haute Qualité / Diversification / Tactical)
    # is collapsed into the public IPS framing: Quality Compounders + Tactical.
    "show_donuts": ["Layer", "Sector", "Thematic", "Geography"],
    "layer_map": {
        "Obvious":         "Quality Compounders",
        "Haute Qualité":   "Quality Compounders",
        "Diversification": "Quality Compounders",
        # Tactical stays Tactical
    },
})
