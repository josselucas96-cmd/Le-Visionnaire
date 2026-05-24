"""Daily refresh of daily_holdings — designed to run from a GitHub Action cron.

Goal
----
After every US market close (or on weekends/holidays), write the day's row
in `daily_holdings` for each portfolio. This makes the public chart EOD-
accurate without depending on visitor traffic (`lazy_write_holdings`, the
visitor-triggered version, has holes when nobody visits the site between
close and midnight).

Runs 7/7 since 2026-05-16. Weekend/holiday rationale: the Nakamoto
benchmark is Bitcoin (24/7). On Sat/Sun, the BTC line extends past the
portfolio line, creating a visual disconnect. By writing weekend rows
that propagate the latest equity close, the portfolio line aligns
timewise with Bitcoin (flat over the weekend, since equities don't move).
Visionnaire/Bâtisseur are unaffected (their benchmarks are 5/7 too).

Run
---
Locally (debug):
    SUPABASE_URL=... SUPABASE_KEY=... python daily_refresh.py
    # or pass --date 2026-05-15 to backfill a specific past day

GitHub Action (production):
    See .github/workflows/daily-refresh.yml — runs daily 22:07 UTC
    (~23-00:00 CH, ~1-2h after US market close on weekdays).

What it writes
--------------
For each portfolio (visionnaire, batisseur, nakamoto):
  - 1 row per active ticker: shares × latest_close ≤ target_date = value
  - 1 CASH row: shares = $ cash, price = 1.0

On weekend/holiday: yfinance has no Close for target_date, so we fall
back to the latest available close ≤ target_date (= previous trading
day). Shares and cash are still derived from the CURRENT positions/
transactions (reflects any moves committed at any time of day).

Cash $ is derived (same logic as utils/data.get_cash_amount):
  - baseline = latest CASH row strictly before target_date
  - + Σ same-day transaction deltas (TRIM/CLOSE proceeds, IN/SWITCH costs)

Idempotent (upsert on portfolio_id, date, ticker).
"""
import argparse
import os
import sys
from datetime import date as _date

import yfinance as yf
from supabase import create_client


INITIAL_CAPITAL_FALLBACK = 1_000_000.0

# PORTFOLIOS is now read dynamically from the `portfolios` table at runtime
# (see `get_all_portfolio_ids` below). This means any new portfolio added to
# the DB — including hidden sandboxes like `test` — is automatically picked
# up on the next cron run without needing a code push.


def get_all_portfolio_ids(sb) -> list[str]:
    """Return all portfolio IDs from the DB (active and inactive).

    Inactive portfolios (e.g., the `test` sandbox with is_active=False) are
    included so the cron keeps their daily_holdings up to date. The Admin
    cockpit shows them; only the public landing filters them out.
    """
    rows = sb.table("portfolios").select("id").order("display_order").execute().data
    return [r["id"] for r in rows]


def fetch_close_price(ticker: str, target_date_str: str, retries: int = 3) -> tuple[float | None, str | None]:
    """Fetch the latest Close ≤ target_date_str.

    On a trading day: returns the close for that day.
    On weekend/holiday: returns the close from the most recent trading day
    before target_date_str (so equity tickers carry forward Friday's close
    into Sat/Sun rows).

    Retries on transient failures (empty result / network / rate-limit).
    yfinance gets rate-limited from GitHub Actions' shared IPs, which caused
    5 days of missing data 2026-05-18→22 (cf. the self-healing backfill below).

    Returns (price, actual_close_date_str) or (None, None) if no data found.
    """
    from datetime import datetime, timedelta
    import time
    import pandas as pd

    target = datetime.strptime(target_date_str, "%Y-%m-%d")
    start = (target - timedelta(days=10)).strftime("%Y-%m-%d")
    end = (target + timedelta(days=1)).strftime("%Y-%m-%d")

    for attempt in range(1, retries + 1):
        try:
            # Fetch a 10-day window ending at target_date to find the latest available
            df = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=False)
            if df.empty or "Close" not in df.columns:
                raise ValueError("empty frame")

            # Keep only rows with date ≤ target_date_str
            df = df[df.index <= pd.Timestamp(target_date_str)]
            if df.empty:
                return None, None  # genuinely no data ≤ target (e.g. pre-listing)

            last_idx = df.index[-1]
            close = df.loc[last_idx, "Close"]
            price = float(close.iloc[0]) if hasattr(close, "iloc") else float(close)
            return price, last_idx.strftime("%Y-%m-%d")
        except Exception as e:
            if attempt < retries:
                time.sleep(2 * attempt)  # 2s, 4s backoff — let rate-limit cool off
                continue
            print(f"  ! {ticker}: yfinance fetch error after {retries} tries ({e})", flush=True)
            return None, None


def get_initial_capital(sb, portfolio_id: str) -> float:
    """Read initial_capital_<pid> setting (with fallback to legacy key for visionnaire)."""
    keys = [f"initial_capital_{portfolio_id}"]
    if portfolio_id == "visionnaire":
        keys.append("initial_capital")
    for k in keys:
        row = sb.table("settings").select("value").eq("key", k).execute().data
        if row and row[0].get("value"):
            try:
                return float(row[0]["value"])
            except (TypeError, ValueError):
                continue
    return INITIAL_CAPITAL_FALLBACK


def derive_cash_at_date(sb, portfolio_id: str, target_date_str: str,
                       initial_capital: float) -> float:
    """Derive cash $ at end of target_date_str, replicating get_cash_amount logic.

    1. Baseline = latest CASH row strictly before target_date_str (or initial_capital)
    2. + Σ same-day transaction $-deltas
    """
    rows = (
        sb.table("daily_holdings")
        .select("date, value")
        .eq("portfolio_id", portfolio_id)
        .eq("ticker", "CASH")
        .lt("date", target_date_str)
        .order("date", desc=True)
        .limit(1)
        .execute()
        .data
    )
    baseline = float(rows[0]["value"]) if rows else float(initial_capital)

    txns = (
        sb.table("transactions")
        .select("action, weight_in, weight_out, price_out, entry_price_out")
        .eq("portfolio_id", portfolio_id)
        .eq("date", target_date_str)
        .execute()
        .data
    )
    delta = 0.0
    for t in txns:
        a = (t.get("action") or "").upper()
        if a == "IN":
            delta -= float(t.get("weight_in") or 0) * initial_capital / 100.0
        elif a in ("TRIM", "OUT"):
            w = float(t.get("weight_out") or 0)
            pru = float(t.get("entry_price_out") or 0)
            p = float(t.get("price_out") or 0)
            if pru > 0:
                delta += (w * initial_capital / 100.0 / pru) * p
        elif a == "SWITCH":
            w_in = float(t.get("weight_in") or 0)
            w_out = float(t.get("weight_out") or 0)
            pru = float(t.get("entry_price_out") or 0)
            p = float(t.get("price_out") or 0)
            if pru > 0:
                delta += (w_out * initial_capital / 100.0 / pru) * p
            delta -= w_in * initial_capital / 100.0
        # DRIP / SPLIT: cash-neutral
    return baseline + delta


def refresh_portfolio(sb, portfolio_id: str, target_date_str: str) -> dict:
    """Write daily_holdings rows for one portfolio. Returns summary dict."""
    initial_capital = get_initial_capital(sb, portfolio_id)
    positions = (
        sb.table("positions")
        .select("ticker, shares")
        .eq("portfolio_id", portfolio_id)
        .eq("is_active", True)
        .execute()
        .data
    )
    cash_amount = derive_cash_at_date(sb, portfolio_id, target_date_str, initial_capital)

    rows = [{
        "portfolio_id": portfolio_id,
        "date":         target_date_str,
        "ticker":       "CASH",
        "shares":       round(cash_amount, 2),
        "price":        1.0,
        "value":        round(cash_amount, 2),
    }]
    nav = cash_amount
    skipped = []
    propagated = []  # tickers where price comes from a date before target
    for p in positions:
        tk = p["ticker"]
        shares = float(p.get("shares") or 0)
        if shares <= 0 or not tk:
            continue
        price, actual_date = fetch_close_price(tk, target_date_str)
        if price is None:
            skipped.append(tk)
            continue
        if actual_date != target_date_str:
            propagated.append((tk, actual_date))
        value = shares * price
        nav += value
        rows.append({
            "portfolio_id": portfolio_id,
            "date":         target_date_str,
            "ticker":       tk,
            "shares":       round(shares, 8),
            "price":        round(price, 4),
            "value":        round(value, 2),
        })

    # Upsert all rows
    sb.table("daily_holdings").upsert(
        rows, on_conflict="portfolio_id,date,ticker"
    ).execute()

    return {
        "portfolio": portfolio_id,
        "rows_written": len(rows),
        "nav": nav,
        "cash": cash_amount,
        "skipped_tickers": skipped,
        "propagated": propagated,
    }


def backfill_recent_gaps(sb, portfolio_ids: list[str], target_date_str: str,
                         lookback_days: int = 7) -> list[dict]:
    """Self-heal: fill any missing (portfolio, date) rows in the last N days.

    Why: a single failed cron run (e.g. yfinance rate-limit from GitHub Actions'
    shared IPs) used to leave a PERMANENT hole — nothing ever went back to fill
    it (cf. the 2026-05-18→22 gap on batisseur/nakamoto). With this, every run
    looks back `lookback_days` calendar days and writes any date a portfolio is
    missing, so a transient failure self-corrects on the next successful run.

    Dates are processed chronologically per portfolio so `derive_cash_at_date`
    chains cash baselines correctly. Existing rows are never overwritten
    (respects the daily_holdings immutability rule — we only ADD missing days).
    """
    from datetime import datetime, timedelta
    target = datetime.strptime(target_date_str, "%Y-%m-%d").date()
    # Candidate dates: [target-lookback, target-1]. `target` itself is written
    # by the main loop, so we don't duplicate it here.
    candidates = [
        (target - timedelta(days=k)).isoformat()
        for k in range(lookback_days, 0, -1)
    ]

    healed = []
    for pid in portfolio_ids:
        # Which of the candidate dates already have rows?
        existing = (
            sb.table("daily_holdings")
            .select("date")
            .eq("portfolio_id", pid)
            .gte("date", candidates[0])
            .lte("date", candidates[-1])
            .execute()
            .data
        )
        present = {r["date"] for r in existing}
        missing = [d for d in candidates if d not in present]
        for d in missing:
            try:
                r = refresh_portfolio(sb, pid, d)
                healed.append({"portfolio": pid, "date": d, "rows": r["rows_written"]})
                print(f"  [backfill] {pid} {d}: wrote {r['rows_written']} rows, "
                      f"NAV=${r['nav']:,.0f}", flush=True)
            except Exception as e:
                print(f"  [backfill] {pid} {d}: ERROR {e}", flush=True)
    return healed


def _compute_dividend_factor(ticker: str, entry_date_str: str) -> tuple[float, float]:
    """Compute (shares_factor, div_return_pct) for one (ticker, entry_date) pair.

    Replicates utils.market.get_total_return_factor logic without Streamlit deps.
    For each dividend paid since entry_date: shares *= (1 + div / price_on_pay_date).

    Returns (1.0, 0.0) if no dividends, ticker has no history, or any error.
    """
    try:
        import pandas as pd
        from datetime import date as _dt
        today_str = _dt.today().isoformat()
        entry_ts = pd.Timestamp(entry_date_str)

        divs = yf.Ticker(ticker).dividends
        if divs.empty:
            return 1.0, 0.0
        if divs.index.tz is not None:
            divs.index = divs.index.tz_localize(None)
        since = divs[divs.index >= entry_ts]
        if since.empty:
            return 1.0, 0.0

        hist = yf.download(ticker, start=entry_date_str, end=today_str,
                           auto_adjust=True, progress=False)
        if hist.empty:
            return 1.0, 0.0
        if isinstance(hist.columns, pd.MultiIndex):
            hist = hist["Close"][ticker]
        else:
            hist = hist["Close"]
        if hist.index.tz is not None:
            hist.index = hist.index.tz_localize(None)

        shares = 1.0
        for pay_date, div in since.items():
            available = hist[hist.index <= pay_date]
            if available.empty:
                continue
            price_on_day = float(available.iloc[-1])
            if price_on_day > 0:
                shares *= (1 + float(div) / price_on_day)

        return round(shares, 6), round((shares - 1) * 100, 4)
    except Exception as e:
        print(f"  ! {ticker}@{entry_date_str}: dividend computation error ({e})", flush=True)
        return 1.0, 0.0


def refresh_dividend_factors(sb, portfolio_ids: list[str]) -> dict:
    """Upsert dividend reinvestment factor per (ticker, entry_date) into
    `dividend_factors`.

    Why: utils.market.get_total_return_factor is the biggest cold-start
    bottleneck on the public site — it calls `yf.Ticker(t).dividends` and
    `yf.download(t, ...)` for each (ticker, entry_date) pair (~50 pairs,
    ~30s total). With this table pre-computed by the cron, the site reads
    it in <100ms.

    Schema: (ticker, entry_date) PK + shares_factor, div_return_pct, fetched_at.
    """
    pairs: set[tuple[str, str]] = set()
    for pid in portfolio_ids:
        rows = (
            sb.table("positions").select("ticker, entry_date")
            .eq("portfolio_id", pid).eq("is_active", True)
            .execute().data
        )
        for r in rows:
            tk = r.get("ticker")
            ed = r.get("entry_date")
            if tk and ed:
                pairs.add((tk, ed))

    print(f"\n[dividend_factors] refreshing {len(pairs)} unique (ticker, entry_date) pairs...", flush=True)

    from datetime import datetime, timezone
    now_iso = datetime.now(timezone.utc).isoformat()
    payload = []
    failed = []

    for ticker, entry_date in sorted(pairs):
        shares_factor, div_return_pct = _compute_dividend_factor(ticker, entry_date)
        if shares_factor == 1.0 and div_return_pct == 0.0:
            # Either truly no dividends (write the row so caller knows it was
            # checked), or an error was logged above. Always write — fallback
            # logic in callers handles both.
            pass
        payload.append({
            "ticker":         ticker,
            "entry_date":     entry_date,
            "shares_factor":  shares_factor,
            "div_return_pct": div_return_pct,
            "fetched_at":     now_iso,
        })

    if payload:
        sb.table("dividend_factors").upsert(
            payload, on_conflict="ticker,entry_date"
        ).execute()
        print(f"[dividend_factors] upserted {len(payload)} rows.", flush=True)
    if failed:
        print(f"[dividend_factors] FAILED: {failed}", flush=True)

    return {"ok": len(payload), "failed": failed}


def refresh_fundamentals(sb, portfolio_ids: list[str]) -> dict:
    """Upsert valuation fundamentals per unique ticker into `fundamentals`.

    Why: utils.market.get_valuation_fundamentals calls `yf.Ticker(t).info` per
    ticker — the SLOWEST yfinance endpoint (5-10s/call) and the most prone to
    rate-limiting. With this table pre-computed nightly, the site reads it in
    <100ms and the cockpit's P/S, Fwd PE, EV/mNAV columns finally fill in
    reliably.

    Fundamentals don't move intraday — daily refresh is plenty.

    Schema: ticker PK + market_cap, enterprise_value, revenue_ttm, ebitda,
    margins (ratios 0-1), free_cashflow, forward_pe, trailing_pe, analyst_rg,
    fetched_at.
    """
    import pandas as pd
    all_tickers: set[str] = set()
    for pid in portfolio_ids:
        rows = (
            sb.table("positions").select("ticker")
            .eq("portfolio_id", pid).eq("is_active", True)
            .execute().data
        )
        for r in rows:
            tk = r.get("ticker")
            if tk:
                all_tickers.add(tk)

    print(f"\n[fundamentals] refreshing {len(all_tickers)} unique tickers (tk.info — slow)...", flush=True)

    from datetime import datetime, timezone
    now_iso = datetime.now(timezone.utc).isoformat()
    payload = []
    failed = []

    for tk in sorted(all_tickers):
        try:
            ticker = yf.Ticker(tk)
            info = ticker.info
            rev = info.get("totalRevenue")
            fcf = info.get("freeCashflow")
            fcf_margin = (fcf / rev) if (rev and fcf is not None and rev > 0) else None

            # Analyst consensus revenue growth (forward, +1y)
            analyst_rg = None
            try:
                rev_est = ticker.revenue_estimate
                if rev_est is not None and not rev_est.empty:
                    if "+1y" in rev_est.index and "growth" in rev_est.columns:
                        g = rev_est.loc["+1y", "growth"]
                        if pd.notna(g):
                            analyst_rg = float(g) * 100
                    if analyst_rg is None and "+1y" in rev_est.index and "0y" in rev_est.index:
                        cur = rev_est.loc["0y", "avg"]
                        nxt = rev_est.loc["+1y", "avg"]
                        if pd.notna(cur) and pd.notna(nxt) and cur > 0:
                            analyst_rg = (float(nxt) - float(cur)) / float(cur) * 100
            except Exception:
                pass
            if analyst_rg is None and info.get("revenueGrowth") is not None:
                analyst_rg = float(info["revenueGrowth"]) * 100

            payload.append({
                "ticker":           tk,
                "market_cap":       float(info["marketCap"]) if info.get("marketCap") is not None else None,
                "enterprise_value": float(info["enterpriseValue"]) if info.get("enterpriseValue") is not None else None,
                "revenue_ttm":      float(rev) if rev is not None else None,
                "ebitda":           float(info["ebitda"]) if info.get("ebitda") is not None else None,
                "gross_margin":     float(info["grossMargins"]) if info.get("grossMargins") is not None else None,
                "operating_margin": float(info["operatingMargins"]) if info.get("operatingMargins") is not None else None,
                "free_cashflow":    float(fcf) if fcf is not None else None,
                "fcf_margin":       float(fcf_margin) if fcf_margin is not None else None,
                "forward_pe":       float(info["forwardPE"]) if info.get("forwardPE") is not None else None,
                "trailing_pe":      float(info["trailingPE"]) if info.get("trailingPE") is not None else None,
                "analyst_rg":       float(analyst_rg) if analyst_rg is not None else None,
                "fetched_at":       now_iso,
            })
        except Exception as e:
            print(f"  ! {tk}: tk.info error ({e})", flush=True)
            failed.append(tk)

    if payload:
        sb.table("fundamentals").upsert(payload, on_conflict="ticker").execute()
        print(f"[fundamentals] upserted {len(payload)} rows.", flush=True)
    if failed:
        print(f"[fundamentals] FAILED: {failed}", flush=True)

    return {"ok": len(payload), "failed": failed}


def refresh_current_prices(sb, portfolio_ids: list[str]) -> dict:
    """Upsert latest price + metadata per unique ticker into `current_prices`.

    Why: visitor pages currently call yfinance directly (1 call per ticker
    × N visitors / cache_TTL). With this table populated nightly, the site
    can read prices from Supabase in 1 query — eliminating Yahoo rate-limit
    risk and dropping page load from ~30s to ~2s.

    Uses fast_info (same source as utils/market.get_prices). During off-hours
    (when this cron runs) fast_info returns the last close.

    Schema: ticker PK + price, change_pct, market_cap, currency, fetched_at.
    """
    # Gather all unique tickers across active positions in all portfolios
    all_tickers: set[str] = set()
    for pid in portfolio_ids:
        rows = (
            sb.table("positions").select("ticker")
            .eq("portfolio_id", pid).eq("is_active", True)
            .execute().data
        )
        for r in rows:
            tk = r.get("ticker")
            if tk:
                all_tickers.add(tk)

    print(f"\n[current_prices] refreshing {len(all_tickers)} unique tickers...", flush=True)

    payload = []
    failed = []
    now_iso = None
    from datetime import datetime, timezone
    now_iso = datetime.now(timezone.utc).isoformat()

    for tk in sorted(all_tickers):
        try:
            info = yf.Ticker(tk).fast_info
            price = info.last_price
            prev = info.previous_close
            if price is None or prev is None:
                failed.append(tk)
                continue
            mc = getattr(info, "market_cap", None)
            ccy = getattr(info, "currency", None) or "USD"
            payload.append({
                "ticker":     tk,
                "price":      round(float(price), 4),
                "change_pct": round((float(price) - float(prev)) / float(prev) * 100, 4) if prev else None,
                "market_cap": float(mc) if mc is not None else None,
                "currency":   ccy,
                "fetched_at": now_iso,
            })
        except Exception as e:
            print(f"  ! {tk}: fast_info error ({e})", flush=True)
            failed.append(tk)

    if payload:
        sb.table("current_prices").upsert(payload, on_conflict="ticker").execute()
        print(f"[current_prices] upserted {len(payload)} rows.", flush=True)
    if failed:
        print(f"[current_prices] FAILED to fetch: {failed}", flush=True)

    return {"ok": len(payload), "failed": failed}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--date", default=None,
        help="Target date YYYY-MM-DD (default: today)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print what would be written; don't touch DB.",
    )
    args = parser.parse_args()

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        print("ERROR: SUPABASE_URL and SUPABASE_KEY env vars are required.", file=sys.stderr)
        sys.exit(2)

    sb = create_client(url, key)
    target = args.date or _date.today().isoformat()
    print(f"[daily_refresh] target date: {target}", flush=True)

    # Probe: can we find any close ≤ target for SPY? (sanity check for very
    # early dates or yfinance being totally down).
    probe_price, probe_date = fetch_close_price("SPY", target)
    if probe_price is None:
        print(f"[daily_refresh] yfinance has no SPY close at all near {target}. "
              f"Likely yfinance is down or target is before 1993. Exiting.", flush=True)
        sys.exit(0)
    if probe_date != target:
        from datetime import datetime
        weekday = datetime.strptime(target, "%Y-%m-%d").weekday()
        label = "weekend" if weekday >= 5 else "US holiday or pre-market"
        print(f"[daily_refresh] {target} is not a trading day ({label}). "
              f"Will propagate the latest close from {probe_date} for all equity tickers.", flush=True)

    if args.dry_run:
        print("[daily_refresh] DRY RUN — no DB writes will happen.", flush=True)

    # Read portfolio IDs from DB dynamically (so new portfolios are auto-picked
    # up without code change — e.g., the `test` sandbox).
    portfolio_ids = get_all_portfolio_ids(sb)
    print(f"[daily_refresh] portfolios to refresh: {portfolio_ids}", flush=True)

    # Self-heal: backfill any missing days from the last week BEFORE writing
    # today's row (chronological order keeps cash baselines correct). This makes
    # the cron resilient to transient failures — a missed day fills itself on the
    # next run instead of leaving a permanent hole.
    if not args.dry_run:
        print(f"\n[daily_refresh] checking last 7 days for gaps to backfill...", flush=True)
        healed = backfill_recent_gaps(sb, portfolio_ids, target, lookback_days=7)
        if healed:
            print(f"[daily_refresh] backfilled {len(healed)} missing (portfolio, date) rows.", flush=True)
        else:
            print(f"[daily_refresh] no gaps found.", flush=True)

    results = []
    for pid in portfolio_ids:
        print(f"\n[{pid}] refreshing {target}...", flush=True)
        try:
            r = refresh_portfolio(sb, pid, target)
            results.append(r)
            print(f"  written {r['rows_written']} rows, NAV=${r['nav']:,.2f}, cash=${r['cash']:,.2f}", flush=True)
            if r.get("propagated"):
                propagated_str = ", ".join(f"{t}<-{d}" for t, d in r["propagated"][:3])
                more = f" (+{len(r['propagated'])-3} more)" if len(r["propagated"]) > 3 else ""
                print(f"  PROPAGATED prices (target was non-trading day): {propagated_str}{more}", flush=True)
            if r["skipped_tickers"]:
                print(f"  SKIPPED (no yfinance data found): {r['skipped_tickers']}", flush=True)
        except Exception as e:
            print(f"  ERROR on {pid}: {e}", file=sys.stderr, flush=True)
            results.append({"portfolio": pid, "error": str(e)})

    # Refresh current_prices (latest price/metadata per ticker, for frontend)
    try:
        cp_result = refresh_current_prices(sb, portfolio_ids)
    except Exception as e:
        print(f"\n[current_prices] refresh failed: {e}", file=sys.stderr, flush=True)
        cp_result = {"ok": 0, "failed": ["(crashed)"]}

    # Refresh dividend_factors (precomputed total return factor per ticker/entry_date)
    try:
        df_result = refresh_dividend_factors(sb, portfolio_ids)
    except Exception as e:
        print(f"\n[dividend_factors] refresh failed: {e}", file=sys.stderr, flush=True)
        df_result = {"ok": 0, "failed": ["(crashed)"]}

    # Refresh fundamentals (P/S, Fwd PE, EV/mNAV, margins, etc — slow tk.info path)
    try:
        fd_result = refresh_fundamentals(sb, portfolio_ids)
    except Exception as e:
        print(f"\n[fundamentals] refresh failed: {e}", file=sys.stderr, flush=True)
        fd_result = {"ok": 0, "failed": ["(crashed)"]}

    # Summary
    print(f"\n[daily_refresh] done. Summary:")
    for r in results:
        if "error" in r:
            print(f"  {r['portfolio']:13} ERROR — {r['error']}")
        else:
            print(f"  {r['portfolio']:13} {r['rows_written']:3} rows  NAV ${r['nav']:>11,.2f}")
    failed_n = len(cp_result.get("failed", []))
    failed_suffix = f" ({failed_n} failed)" if failed_n else ""
    print(f"  current_prices    {cp_result['ok']:3} tickers updated{failed_suffix}")
    df_failed_n = len(df_result.get("failed", []))
    df_failed_suffix = f" ({df_failed_n} failed)" if df_failed_n else ""
    print(f"  dividend_factors  {df_result['ok']:3} pairs updated{df_failed_suffix}")
    fd_failed_n = len(fd_result.get("failed", []))
    fd_failed_suffix = f" ({fd_failed_n} failed)" if fd_failed_n else ""
    print(f"  fundamentals      {fd_result['ok']:3} tickers updated{fd_failed_suffix}")

    # Exit with non-zero if any portfolio failed
    if any("error" in r for r in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
