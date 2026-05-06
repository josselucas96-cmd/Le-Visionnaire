"""Specula utilities package."""
from pathlib import Path

# Project root (Streamlit_project/), resolved from this file's location so
# every page can reference the favicon regardless of the cwd Streamlit Cloud
# happens to be using at runtime.
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPECULA_ICON = str(_PROJECT_ROOT / "static" / "specula_favicon.png")
