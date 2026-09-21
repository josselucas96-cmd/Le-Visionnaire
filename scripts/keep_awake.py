"""Keep the public Streamlit app awake with a real browser visit.

Why
---
Streamlit Community Cloud puts an app to sleep after 12 hours without traffic
(threshold lowered from 24h in March 2025). A sleeping app greets visitors with
"Zzzz… get this app back up" and a ~1 minute cold start — unacceptable for a
public track record. Per Streamlit staff, what resets the countdown is a real
visit (or a commit). A plain HTTP GET is not confirmed to count, so we open the
landing page in headless Chromium (a genuine websocket session), and if the
app is asleep we click the wake-up button ourselves.

Scheduled every 6 hours by .github/workflows/keep-awake.yml — comfortably
under the 12h threshold even when GitHub delays a cron run by a few hours.
It does NOT write anything: daily_holdings is written by daily_refresh.py only.

Exit code is non-zero when the page could not be reached at all, so the
watchdog / GitHub notifications surface an outage instead of hiding it.
"""
import os
import sys

from playwright.sync_api import sync_playwright

APP_URL = os.environ.get("APP_URL", "https://specula-project.streamlit.app/")
# "Ready" = the app's own content is on screen (the landing page always shows
# the Specula title + THE PORTFOLIOS section). Streamlit's internal test-ids
# vary across versions/custom layouts, so we look at rendered text instead.
# Landing page shows "THE PORTFOLIOS"; any other page shows the nav (Accueil/About) — either counts.
READY_JS = "() => /Specula/.test(document.body.innerText) && /(PORTFOLIO|Accueil|Page not found)/i.test(document.body.innerText)"


def wait_until_rendered(page, timeout_ms: int) -> bool:
    """On *.streamlit.app the app runs inside an iframe of a wrapper page, so
    the top document never contains the app's text: poll EVERY frame."""
    import time
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        for frame in page.frames:
            try:
                if frame.evaluate(READY_JS):
                    return True
            except Exception:
                pass
        page.wait_for_timeout(2_000)
    return False


def wake_if_asleep(page) -> bool:
    for label in ("Yes, get this app back up!", "get this app back up"):
        try:
            btn = page.get_by_role("button", name=label)
            if btn.count() > 0 and btn.first.is_visible():
                print("app was ASLEEP -> clicking the wake button", flush=True)
                btn.first.click()
                return True
        except Exception:
            continue
    return False


def main() -> int:
    print(f"visiting {APP_URL}", flush=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_context(viewport={"width": 1280, "height": 900}).new_page()
        try:
            page.goto(APP_URL, timeout=120_000, wait_until="domcontentloaded")
            woke = wake_if_asleep(page)
            # A cold start after waking can take ~1-2 min; be patient.
            if not wait_until_rendered(page, 180_000 if woke else 90_000):
                raise TimeoutError("app content not found in any frame")
            page.wait_for_timeout(8_000)  # let the script run so the session counts as traffic
            title = page.title()
            texts = " ".join((f.evaluate("() => document.body.innerText") or "") for f in page.frames)
            nav = [w for w in ("Accueil", "Moves", "Stock Papers", "Articles", "About") if w in texts]
            print(f"app rendered (title: {title!r}){' after wake-up' if woke else ''} | nav items seen: {nav} | page-not-found: {'Page not found' in texts}", flush=True)
            return 0
        except Exception as e:
            print(f"ERROR: app did not render: {e}", flush=True)
            try:
                page.screenshot(path="keep_awake_failure.png", full_page=True)
            except Exception:
                pass
            return 1
        finally:
            browser.close()


if __name__ == "__main__":
    sys.exit(main())
