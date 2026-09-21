"""Independent morning health check for the Specula pipeline.

The September 2026 outage went unnoticed for 18 days because nothing watched
the watcher: the cron had been switched off by GitHub and the site kept saying
"Last updated <today>". This script runs on its own schedule and FAILS LOUDLY
(non-zero exit => red run => GitHub e-mails the repo owner) when:

  1. any portfolio is missing yesterday's daily_holdings row
     (the cron writes 7/7, so by 06:40 UTC yesterday must be there);
  2. current_prices has not been refreshed in the last 36 hours;
  3. the daily-refresh workflow is not `active` (GitHub disables scheduled
     workflows after 60 idle days — exactly what happened on 2026-09-01);
  4. the public app URL does not serve the app (e.g. the subdomain 404s).

It only READS. Env: SUPABASE_URL, SUPABASE_KEY (anon), GITHUB_TOKEN,
GITHUB_REPOSITORY (set by Actions), APP_URL.
"""
import json
import os
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone

from supabase import create_client

APP_URL = os.environ.get("APP_URL", "https://specula-project.streamlit.app/")
REPO = os.environ.get("GITHUB_REPOSITORY", "josselucas96-cmd/Specula")
problems, notes, alerts = [], [], []

# Management alerts (not pipeline failures): thresholds per portfolio, in %.
# A breach opens a GitHub issue (owner gets the notification) instead of
# failing the run, which is reserved for "the pipeline is broken".
DRAWDOWN_THRESHOLDS = {"default": (-5.0, -15.0), "nakamoto": (-10.0, -30.0)}   # (1-day move, drawdown from peak)


def check_holdings(sb):
    yesterday = (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()
    pids = [r["id"] for r in sb.table("portfolios").select("id").execute().data]
    for pid in pids:
        last = sb.table("daily_holdings").select("date").eq("portfolio_id", pid) \
                 .order("date", desc=True).limit(1).execute().data
        last_date = last[0]["date"] if last else None
        if last_date is None or last_date < yesterday:
            problems.append(f"daily_holdings: {pid} last row = {last_date}, expected >= {yesterday}")
        else:
            notes.append(f"{pid}: last row {last_date}")


def check_prices(sb):
    r = sb.table("current_prices").select("fetched_at").order("fetched_at", desc=True).limit(1).execute().data
    if not r:
        problems.append("current_prices: table empty"); return
    ts = datetime.fromisoformat(r[0]["fetched_at"].replace("Z", "+00:00"))
    age_h = (datetime.now(timezone.utc) - ts).total_seconds() / 3600
    (problems if age_h > 36 else notes).append(f"current_prices: last refresh {age_h:.0f}h ago")


def check_drawdowns(sb):
    """1-day move and drawdown from the running peak, per active portfolio."""
    pids = [r["id"] for r in sb.table("portfolios").select("id").eq("is_active", True).execute().data]
    for pid in pids:
        rows, off = [], 0
        while True:
            r = (sb.table("daily_holdings").select("date,value").eq("portfolio_id", pid)
                 .order("date").order("ticker").range(off, off + 999).execute().data)
            rows += r
            if len(r) < 1000:
                break
            off += 1000
        nav = {}
        for r in rows:
            nav[r["date"]] = nav.get(r["date"], 0.0) + float(r["value"] or 0)
        dates = sorted(nav)
        if len(dates) < 3:
            continue
        last, prev = nav[dates[-1]], nav[dates[-2]]
        peak = max(nav.values())
        day = (last / prev - 1) * 100 if prev else 0.0
        dd = (last / peak - 1) * 100 if peak else 0.0
        t_day, t_dd = DRAWDOWN_THRESHOLDS.get(pid, DRAWDOWN_THRESHOLDS["default"])
        line = f"{pid}: {dates[-1]} NAV ${last:,.0f}, 1-day {day:+.2f}%, drawdown from peak {dd:+.2f}%"
        if day <= t_day or dd <= t_dd:
            alerts.append(line + f"  (thresholds {t_day:+.0f}% / {t_dd:+.0f}%)")
        else:
            notes.append(line)


def _gh_post(path, payload):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"https://api.github.com/repos/{REPO}/{path}", data=data, method="POST",
        headers={"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}", "Accept": "application/vnd.github+json",
                 "Content-Type": "application/json", "User-Agent": "specula-watchdog"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def raise_drawdown_issue():
    """One issue per day at most; skipped without a token (local runs)."""
    if not alerts or not os.environ.get("GITHUB_TOKEN"):
        return
    today = date.today().isoformat()
    title = f"Alerte drawdown — {today}"
    try:
        existing = _gh(f"issues?state=open&labels=alerte&per_page=20")
        if any(i.get("title") == title for i in existing):
            notes.append("drawdown issue already open today"); return
        body = ("Le watchdog a relevé un mouvement ou un drawdown au-delà des seuils :\n\n"
                + "\n".join(f"- {a}" for a in alerts)
                + "\n\nCe n'est pas une panne du pipeline. À toi de juger : revue de la position, du sizing, ou rien. "
                  "Fermer l'issue une fois vue. Seuils dans `scripts/watchdog.py` (`DRAWDOWN_THRESHOLDS`).")
        _gh_post("issues", {"title": title, "body": body, "labels": ["alerte"]})
        notes.append(f"drawdown issue opened: {title}")
    except Exception as e:
        problems.append(f"could not open drawdown issue: {e}")


def _gh(path):
    req = urllib.request.Request(
        f"https://api.github.com/repos/{REPO}/{path}",
        headers={"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
                 "Accept": "application/vnd.github+json", "User-Agent": "specula-watchdog"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def check_workflow():
    if not os.environ.get("GITHUB_TOKEN"):
        notes.append("workflow state: skipped (no GITHUB_TOKEN)"); return
    try:
        wf = _gh("actions/workflows/daily-refresh.yml")
        if wf.get("state") != "active":
            problems.append(f"daily-refresh workflow state = {wf.get('state')} (re-enable: gh workflow enable daily-refresh.yml)")
        runs = _gh("actions/workflows/daily-refresh.yml/runs?per_page=1&event=schedule").get("workflow_runs", [])
        if runs:
            r = runs[0]
            line = f"last scheduled daily-refresh: {r['created_at'][:16]} -> {r['conclusion']}"
            (notes if r["conclusion"] == "success" else problems).append(line)
        # keep-awake must have visited the app in the last 12h (Streamlit sleeps
        # after 12h without traffic); GitHub sometimes delays or drops crons.
        ka = _gh("actions/workflows/keep-awake.yml/runs?per_page=1&status=success").get("workflow_runs", [])
        if ka:
            ts = datetime.fromisoformat(ka[0]["created_at"].replace("Z", "+00:00"))
            age_h = (datetime.now(timezone.utc) - ts).total_seconds() / 3600
            (problems if age_h > 12 else notes).append(f"last successful keep-awake visit {age_h:.1f}h ago")
        else:
            problems.append("keep-awake: no successful run found")
    except Exception as e:
        problems.append(f"GitHub API check failed: {e}")


def check_app():
    """Follow Streamlit's auth redirect with a cookie jar; a live public app ends
    on 200 HTML, a dead subdomain ends on share.streamlit.io/errors/not_found."""
    import http.cookiejar
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    try:
        resp = opener.open(urllib.request.Request(APP_URL, headers={"User-Agent": "Mozilla/5.0 specula-watchdog"}), timeout=60)
        final, code = resp.geturl(), resp.getcode()
        body = resp.read(200_000).decode("utf-8", "ignore")
        if code != 200 or "errors/not_found" in final or "does not exist" in body:
            problems.append(f"app URL {APP_URL} -> {code} at {final}")
        else:
            notes.append(f"app URL ok ({code}, {final})")
    except Exception as e:
        problems.append(f"app URL {APP_URL} unreachable: {e}")


def main() -> int:
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
    check_holdings(sb)
    check_prices(sb)
    check_workflow()
    check_app()
    check_drawdowns(sb)
    raise_drawdown_issue()
    print(f"[watchdog] {date.today()} UTC")
    for n in notes:
        print("  ok   ", n)
    for a in alerts:
        print("  ALERT", a)
    for p in problems:
        print("  FAIL ", p)
    if problems:
        print(f"\n[watchdog] {len(problems)} problem(s) -> failing so GitHub notifies the owner.")
        return 1
    print("\n[watchdog] all green.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
