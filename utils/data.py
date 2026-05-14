"""Supabase data layer with portfolio scoping (multi-portfolio aware).

Move semantics (PR-3):
- Every move on a position keeps `weight`, `entry_price` (PRU) AND `units`
  in sync. `units = weight / PRU` for invariance.
- `cash_units` on the portfolio row is mutated by delta on each move (not
  derived from weights) so dividends and external capital can be modelled
  without violating the invariant.
- PRU on REINFORCE uses the shares-weighted average (total cost / total
  units) — the mathematically correct formula. The legacy NAV-weighted
  formula was off by a small amount whenever reinforce price ≠ original
  PRU.
"""
import streamlit as st
from supabase import create_client


@st.cache_resource
def get_client():
    return create_client(st.secrets["supabase_url"], st.secrets["supabase_key"])


# ── Internal helpers ──────────────────────────────────────────────────────────
def _adjust_cash_units(sb, portfolio_id: str, delta: float) -> None:
    """Add `delta` to portfolios.cash_units atomically (read-modify-write)."""
    row = (
        sb.table("portfolios")
        .select("cash_units")
        .eq("id", portfolio_id)
        .execute()
        .data
    )
    if not row:
        return
    old = float(row[0].get("cash_units") or 0)
    sb.table("portfolios").update({
        "cash_units": round(old + delta, 6),
    }).eq("id", portfolio_id).execute()


def _existing_units(row: dict) -> float:
    """Resolve units from a position row. Falls back to weight/entry_price
    when the column was not yet backfilled (defensive)."""
    u = row.get("units")
    if u is not None:
        return float(u)
    w = float(row.get("weight") or 0)
    p = float(row.get("entry_price") or 0)
    return (w / p) if p > 0 else 0.0


# ── Portfolios ────────────────────────────────────────────────────────────────
def get_portfolios(active_only=True):
    """List all portfolios, ordered by display_order."""
    sb = get_client()
    query = sb.table("portfolios").select("*").order("display_order")
    if active_only:
        query = query.eq("is_active", True)
    return query.execute().data


def get_portfolio(portfolio_id: str):
    """Fetch a single portfolio's metadata by id (slug)."""
    sb = get_client()
    result = sb.table("portfolios").select("*").eq("id", portfolio_id).execute().data
    return result[0] if result else None


def update_portfolio(portfolio_id: str, fields: dict):
    """Update fields on a portfolio row (name, inception_date, etc.)."""
    sb = get_client()
    sb.table("portfolios").update(fields).eq("id", portfolio_id).execute()


def update_position_valuation(position_id: int, growth, gm, om, fcf):
    """Persist the user's expected forward valuation inputs on a position.

    growth, gm, om, fcf are percentages (e.g. 20.0 = 20%). None values are
    stored as NULL — clearing a cell removes the estimate.
    """
    sb = get_client()
    sb.table("positions").update({
        "expected_revenue_growth": growth,
        "expected_gross_margin":   gm,
        "expected_op_margin":      om,
        "expected_fcf_margin":     fcf,
    }).eq("id", position_id).execute()


# ── Positions ─────────────────────────────────────────────────────────────────
def get_positions(active_only=True, portfolio_id: str = "visionnaire"):
    sb = get_client()
    query = sb.table("positions").select("*").eq("portfolio_id", portfolio_id)
    if active_only:
        query = query.eq("is_active", True)
    return query.order("ticker").execute().data


def get_transactions(portfolio_id: str = "visionnaire"):
    sb = get_client()
    return (
        sb.table("transactions")
        .select("*")
        .eq("portfolio_id", portfolio_id)
        .order("date", desc=True)
        .execute()
        .data
    )


# ── Settings (global for now; will scope later if needed) ─────────────────────
def get_setting(key, default=None):
    sb = get_client()
    result = sb.table("settings").select("value").eq("key", key).execute().data
    return result[0]["value"] if result else default


def upsert_setting(key, value):
    sb = get_client()
    sb.table("settings").upsert({"key": key, "value": str(value)}).execute()


# ── Position write operations ─────────────────────────────────────────────────
def add_position(data: dict, portfolio_id: str = "visionnaire"):
    sb = get_client()
    data = {**data, "portfolio_id": portfolio_id}

    existing = (
        sb.table("positions")
        .select("id, weight, entry_price, units")
        .eq("portfolio_id", portfolio_id)
        .eq("ticker", data["ticker"])
        .eq("is_active", True)
        .execute()
        .data
    )
    new_w = float(data["weight"])
    new_p = float(data["entry_price"])
    new_units = round(new_w / new_p, 8) if new_p > 0 else 0.0

    if existing:
        # REINFORCE — shares-weighted PRU averaging
        ex = existing[0]
        old_w = float(ex["weight"])
        old_units = _existing_units(ex)
        total_w = round(old_w + new_w, 4)
        total_units = round(old_units + new_units, 8)
        new_pru = round(total_w / total_units, 6) if total_units > 0 else 0.0

        update_data = {
            "weight":      total_w,
            "entry_price": new_pru,
            "units":       total_units,
        }
        new_thesis = (data.get("thesis_short") or "").strip()
        if new_thesis:
            update_data["thesis_short"] = new_thesis
        sb.table("positions").update(update_data).eq("id", ex["id"]).execute()
        sb.table("transactions").insert({
            "portfolio_id": portfolio_id,
            "date":         data.get("entry_date"),
            "action":       "IN",
            "ticker_in":    data["ticker"],
            "price_in":     new_p,
            "weight_in":    new_w,
            "reason":       f"Reinforced {new_w}% (new PRU: {new_pru:.4f})",
        }).execute()
    else:
        # NEW POSITION
        data = {**data, "units": new_units}
        sb.table("positions").insert(data).execute()
        sb.table("transactions").insert({
            "portfolio_id": portfolio_id,
            "date":         data.get("entry_date"),
            "action":       "IN",
            "ticker_in":    data.get("ticker"),
            "price_in":     new_p,
            "weight_in":    new_w,
            "reason":       "New position",
        }).execute()

    # Cost of the new exposure leaves cash
    _adjust_cash_units(sb, portfolio_id, -new_w)


def trim_position(position_id: int, weight_sold: float, exit_price: float,
                  exit_date: str, reason: str):
    sb = get_client()
    pos = sb.table("positions").select("*").eq("id", position_id).execute().data[0]
    old_w = float(pos["weight"])
    new_w = round(old_w - weight_sold, 4)
    old_units = _existing_units(pos)
    # Proportional unit reduction → PRU intact
    new_units = round(old_units * (new_w / old_w), 8) if old_w > 0 else 0.0
    perf = round((exit_price - pos["entry_price"]) / pos["entry_price"] * 100, 2)

    sb.table("positions").update({
        "weight": new_w,
        "units":  new_units,
    }).eq("id", position_id).execute()
    sb.table("transactions").insert({
        "portfolio_id":    pos.get("portfolio_id", "visionnaire"),
        "date":            exit_date,
        "action":          "TRIM",
        "ticker_out":      pos["ticker"],
        "price_out":       exit_price,
        "entry_price_out": pos["entry_price"],
        "weight_out":      weight_sold,
        "perf_pct":        perf,
        "reason":          reason,
    }).execute()

    # Cost basis returned to cash (proceeds at cost; realized P&L not booked).
    _adjust_cash_units(sb, pos.get("portfolio_id", "visionnaire"), weight_sold)


def close_position(position_id: int, exit_price: float, exit_date: str, reason: str):
    sb = get_client()
    pos = sb.table("positions").select("*").eq("id", position_id).execute().data[0]
    old_w = float(pos["weight"])
    perf = round((exit_price - pos["entry_price"]) / pos["entry_price"] * 100, 2)

    sb.table("transactions").insert({
        "portfolio_id":    pos.get("portfolio_id", "visionnaire"),
        "date":            exit_date,
        "action":          "OUT",
        "ticker_out":      pos["ticker"],
        "price_out":       exit_price,
        "entry_price_out": pos["entry_price"],
        "weight_out":      old_w,
        "perf_pct":        perf,
        "reason":          reason,
    }).execute()
    sb.table("positions").update({
        "is_active":  False,
        "exit_price": exit_price,
        "exit_date":  exit_date,
        "units":      0,
    }).eq("id", position_id).execute()

    _adjust_cash_units(sb, pos.get("portfolio_id", "visionnaire"), old_w)


def switch_position(out_id: int, out_price: float, in_data: dict,
                    date: str, reason: str):
    sb = get_client()
    pos_out = sb.table("positions").select("*").eq("id", out_id).execute().data[0]
    portfolio_id = pos_out.get("portfolio_id", "visionnaire")
    out_w = float(pos_out["weight"])
    perf = round((out_price - pos_out["entry_price"]) / pos_out["entry_price"] * 100, 2)

    sb.table("transactions").insert({
        "portfolio_id":    portfolio_id,
        "date":            date,
        "action":          "SWITCH",
        "ticker_out":      pos_out["ticker"],
        "price_out":       out_price,
        "weight_out":      out_w,
        "ticker_in":       in_data["ticker"],
        "price_in":        in_data["entry_price"],
        "weight_in":       in_data["weight"],
        "entry_price_out": pos_out["entry_price"],
        "perf_pct":        perf,
        "reason":          reason,
    }).execute()
    sb.table("positions").update({
        "is_active":  False,
        "exit_price": out_price,
        "exit_date":  date,
        "units":      0,
    }).eq("id", out_id).execute()

    new_w = float(in_data["weight"])
    new_p = float(in_data["entry_price"])
    new_units = round(new_w / new_p, 8) if new_p > 0 else 0.0
    sb.table("positions").insert({
        **in_data, "portfolio_id": portfolio_id, "units": new_units,
    }).execute()

    # Net cash flow: cost-basis recovered from out, cost-basis consumed by in
    _adjust_cash_units(sb, portfolio_id, out_w - new_w)


# ── Corporate actions ─────────────────────────────────────────────────────────
def apply_dividend_drip(portfolio_id: str, ticker: str, div_per_share: float,
                        reinvest_price: float | None = None,
                        payment_date: str | None = None):
    """Apply a dividend with automatic reinvestment (DRIP).

    cash_received = units × div_per_share
    new units purchased at reinvest_price (default = current PRU)
    Weight (cost basis) grows by cash_received. Cash position unchanged.
    PRU recomputes to weight / total_units. Returns the cash_received amount.
    """
    sb = get_client()
    pos = (
        sb.table("positions")
        .select("*")
        .eq("portfolio_id", portfolio_id)
        .eq("ticker", ticker)
        .eq("is_active", True)
        .execute()
        .data
    )
    if not pos:
        return None
    p = pos[0]
    old_units = _existing_units(p)
    if old_units <= 0 or div_per_share <= 0:
        return None
    if reinvest_price is None or reinvest_price <= 0:
        reinvest_price = float(p["entry_price"])

    cash_received   = old_units * div_per_share
    new_units_added = cash_received / reinvest_price
    total_units     = round(old_units + new_units_added, 8)
    new_weight      = round(float(p["weight"]) + cash_received, 4)
    new_pru         = round(new_weight / total_units, 6) if total_units > 0 else 0.0

    sb.table("positions").update({
        "units":       total_units,
        "weight":      new_weight,
        "entry_price": new_pru,
    }).eq("id", p["id"]).execute()

    if payment_date is None:
        from datetime import date as _date
        payment_date = _date.today().isoformat()

    sb.table("transactions").insert({
        "portfolio_id": portfolio_id,
        "date":         payment_date,
        "action":       "DRIP",
        "ticker_in":    ticker,
        "price_in":     reinvest_price,
        "weight_in":    cash_received,
        "reason":       (f"DRIP ${div_per_share:.4f}/share × {old_units:.6f} units "
                         f"= ${cash_received:.4f} reinvested @ ${reinvest_price:.4f}"),
    }).execute()
    # cash_units unchanged: DRIP is cash-neutral (dividend received then spent).
    return cash_received


def apply_split(portfolio_id: str, ticker: str, ratio: float,
                split_date: str | None = None):
    """Apply a stock split (or reverse split if ratio < 1).

    units × ratio, PRU ÷ ratio, weight unchanged. Logs a transaction with
    action='SPLIT'.
    """
    sb = get_client()
    pos = (
        sb.table("positions")
        .select("*")
        .eq("portfolio_id", portfolio_id)
        .eq("ticker", ticker)
        .eq("is_active", True)
        .execute()
        .data
    )
    if not pos or ratio <= 0:
        return None
    p = pos[0]
    old_units = _existing_units(p)
    new_units = round(old_units * ratio, 8)
    new_pru   = round(float(p["entry_price"]) / ratio, 6)

    sb.table("positions").update({
        "units":       new_units,
        "entry_price": new_pru,
    }).eq("id", p["id"]).execute()

    if split_date is None:
        from datetime import date as _date
        split_date = _date.today().isoformat()

    sb.table("transactions").insert({
        "portfolio_id": portfolio_id,
        "date":         split_date,
        "action":       "SPLIT",
        "ticker_in":    ticker,
        "price_in":     new_pru,
        "reason":       f"{ratio}-for-1 split: units × {ratio}, PRU ÷ {ratio}",
    }).execute()
    return new_units


# ── Events (global for now) ───────────────────────────────────────────────────
def get_events():
    sb = get_client()
    return sb.table("events").select("*").order("event_date").execute().data


def add_event(data: dict):
    sb = get_client()
    sb.table("events").insert(data).execute()


def delete_event(event_id: int):
    sb = get_client()
    sb.table("events").delete().eq("id", event_id).execute()


# ── Reset ─────────────────────────────────────────────────────────────────────
def reset_portfolio(today_str: str, prices: dict, portfolio_id: str = "visionnaire"):
    """
    Reinitialize portfolio for a fresh start:
    - Reset entry_price and entry_date to today's price for all active positions
    - Recompute units from new weight/entry_price
    - Deactivate STRC cleanly (no exit transaction — it's a reset, not a trade)
    - Update inception_date in both settings (legacy) and portfolios table.
    - Recompute cash_units = 100 - Σ active weights.
    """
    sb = get_client()
    positions = get_positions(portfolio_id=portfolio_id)
    total_w_active = 0.0
    for p in positions:
        ticker = p["ticker"]
        if ticker == "STRC":
            sb.table("positions").update({"is_active": False, "units": 0}).eq("id", p["id"]).execute()
            continue
        current_price = prices.get(ticker)
        if not current_price:
            total_w_active += float(p.get("weight") or 0)
            continue
        w = float(p.get("weight") or 0)
        units = round(w / current_price, 8) if current_price > 0 else 0.0
        sb.table("positions").update({
            "entry_price": current_price,
            "entry_date":  today_str,
            "units":       units,
        }).eq("id", p["id"]).execute()
        total_w_active += w
    sb.table("portfolios").update({
        "inception_date": today_str,
        "cash_units":     round(100.0 - total_w_active, 6),
    }).eq("id", portfolio_id).execute()
