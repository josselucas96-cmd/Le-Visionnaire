"""Ping the public portfolio pages with a real (headless) browser so Streamlit
runs the page script — which calls lazy_write_holdings and writes today's
daily_holdings row.

Why this exists
---------------
The daily_refresh.py cron runs on GitHub Actions, whose shared IPs get
rate-limited by Yahoo Finance → the cron fails (confirmed: the same code
succeeds from other IPs). lazy_write_holdings, triggered when a visitor opens
a portfolio page, runs on STREAMLIT CLOUD's IP (not rate-limited) and keeps
daily_holdings fresh — that's why Le Visionnaire (most visited) stays current
while the less-visited portfolios lag.

This script automates the "visit": GitHub Actions drives a headless browser
that loads each page. The browser runs on GitHub's IP, but the page's Python
(and the yfinance calls) run on Streamlit Cloud's IP → no Yahoo rate-limit.

A plain HTTP GET (curl) is NOT enough: Streamlit only runs the script for a
real browser session (websocket), so we need Playwright/Chromium.

Scope / known limits
---------------------
- Covers daily_holdings (the charts) only — NOT current_prices / fundamentals
  (those are separate tables written by daily_refresh.py).
- lazy_write only writes when yfinance has today's close, so this is a no-op on
  weekends/holidays (harmless — the equity charts are weekday-only anyway).
- Interim band-aid. The real fix is a reliable data source (see the
  data-pipeline hardening work).
"""
import sys

from playwright.sync_api import sync_playwright

BASE = "https://le-visionnaire-2uegahhgenoesza6ux4ys3.streamlit.app"
PAGES = ["/Visionnaire", "/Batisseur", "/Nakamoto"]


def wake_if_asleep(page):
    """Streamlit Community Cloud shows a wake-up button when the app has slept.
    Click it if present so the app spins back up."""
    for label in ("Yes, get this app back up!", "get this app back up"):
        try:
            btn = page.get_by_role("button", name=label)
            if btn.count() > 0 and btn.first.is_visible():
                print("  app asleep -> clicking wake button", flush=True)
                btn.first.click()
                page.wait_for_timeout(8000)
                return
        except Exception:
            continue


def ping(page, url):
    print(f"Loading {url}", flush=True)
    page.goto(url, timeout=120000, wait_until="domcontentloaded")
    wake_if_asleep(page)
    # render_portfolio_page calls lazy_write_holdings BEFORE drawing the chart,
    # so a visible Plotly chart means today's row has been written server-side.
    try:
        page.wait_for_selector(".js-plotly-plot", timeout=120000)
        print("  chart rendered (lazy_write has run)", flush=True)
    except Exception:
        print("  WARNING: chart not detected; fallback wait 45s", flush=True)
        page.wait_for_timeout(45000)
    page.wait_for_timeout(5000)  # buffer so the DB write commits


def main():
    ok = True
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1280, "height": 1000})
        for path in PAGES:
            page = ctx.new_page()
            try:
                ping(page, BASE + path)
                print(f"  done {path}", flush=True)
            except Exception as e:
                print(f"  ERROR on {path}: {e}", flush=True)
                ok = False
            finally:
                page.close()
        browser.close()
    print("Ping run complete." if ok else "Ping run finished with errors.", flush=True)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
