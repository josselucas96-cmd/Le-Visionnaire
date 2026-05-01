import streamlit as st
from supabase import create_client


@st.cache_resource
def get_client():
    return create_client(st.secrets["supabase_url"], st.secrets["supabase_key"])


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
    # Ensure portfolio_id is on the inserted row
    data = {**data, "portfolio_id": portfolio_id}

    existing = (
        sb.table("positions")
        .select("id, weight, entry_price")
        .eq("portfolio_id", portfolio_id)
        .eq("ticker", data["ticker"])
        .eq("is_active", True)
        .execute()
        .data
    )
    if existing:
        ex = existing[0]
        old_w = float(ex["weight"])
        new_w = float(data["weight"])
        total_w = old_w + new_w
        pru = round((old_w * float(ex["entry_price"]) + new_w * float(data["entry_price"])) / total_w, 4)
        update_data = {"weight": total_w, "entry_price": pru}
        new_thesis = (data.get("thesis_short") or "").strip()
        if new_thesis:
            update_data["thesis_short"] = new_thesis
        sb.table("positions").update(update_data).eq("id", ex["id"]).execute()
        sb.table("transactions").insert({
            "portfolio_id": portfolio_id,
            "date": data.get("entry_date"),
            "action": "IN",
            "ticker_in": data["ticker"],
            "price_in": data.get("entry_price"),
            "weight_in": new_w,
            "reason": f"Added {new_w}% to existing position (new PRU: {pru})",
        }).execute()
    else:
        sb.table("positions").insert(data).execute()
        sb.table("transactions").insert({
            "portfolio_id": portfolio_id,
            "date": data.get("entry_date"),
            "action": "IN",
            "ticker_in": data.get("ticker"),
            "price_in": data.get("entry_price"),
            "weight_in": data.get("weight"),
            "reason": "New position",
        }).execute()


def trim_position(position_id: int, weight_sold: float, exit_price: float, exit_date: str, reason: str):
    sb = get_client()
    pos = sb.table("positions").select("*").eq("id", position_id).execute().data[0]
    perf = round((exit_price - pos["entry_price"]) / pos["entry_price"] * 100, 2)
    new_weight = round(pos["weight"] - weight_sold, 4)
    sb.table("positions").update({"weight": new_weight}).eq("id", position_id).execute()
    sb.table("transactions").insert({
        "portfolio_id": pos.get("portfolio_id", "visionnaire"),
        "date": exit_date,
        "action": "TRIM",
        "ticker_out": pos["ticker"],
        "price_out": exit_price,
        "entry_price_out": pos["entry_price"],
        "weight_out": weight_sold,
        "perf_pct": perf,
        "reason": reason,
    }).execute()


def close_position(position_id: int, exit_price: float, exit_date: str, reason: str):
    sb = get_client()
    pos = sb.table("positions").select("*").eq("id", position_id).execute().data[0]
    perf = round((exit_price - pos["entry_price"]) / pos["entry_price"] * 100, 2)
    sb.table("transactions").insert({
        "portfolio_id": pos.get("portfolio_id", "visionnaire"),
        "date": exit_date,
        "action": "OUT",
        "ticker_out": pos["ticker"],
        "price_out": exit_price,
        "entry_price_out": pos["entry_price"],
        "weight_out": pos["weight"],
        "perf_pct": perf,
        "reason": reason,
    }).execute()
    sb.table("positions").update({
        "is_active": False,
        "exit_price": exit_price,
        "exit_date": exit_date,
    }).eq("id", position_id).execute()


def switch_position(out_id: int, out_price: float, in_data: dict, date: str, reason: str):
    sb = get_client()
    pos_out = sb.table("positions").select("*").eq("id", out_id).execute().data[0]
    portfolio_id = pos_out.get("portfolio_id", "visionnaire")
    perf = round((out_price - pos_out["entry_price"]) / pos_out["entry_price"] * 100, 2)
    sb.table("transactions").insert({
        "portfolio_id": portfolio_id,
        "date": date,
        "action": "SWITCH",
        "ticker_out": pos_out["ticker"],
        "price_out": out_price,
        "weight_out": pos_out["weight"],
        "ticker_in": in_data["ticker"],
        "price_in": in_data["entry_price"],
        "weight_in": in_data["weight"],
        "entry_price_out": pos_out["entry_price"],
        "perf_pct": perf,
        "reason": reason,
    }).execute()
    sb.table("positions").update({
        "is_active": False,
        "exit_price": out_price,
        "exit_date": date,
    }).eq("id", out_id).execute()
    # Ensure new position carries the same portfolio_id as the one being switched out
    sb.table("positions").insert({**in_data, "portfolio_id": portfolio_id}).execute()


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
    - Deactivate STRC cleanly (no exit transaction — it's a reset, not a trade)
    - Update inception_date in both settings (legacy) and portfolios table.
    """
    sb = get_client()
    positions = get_positions(portfolio_id=portfolio_id)
    for p in positions:
        ticker = p["ticker"]
        if ticker == "STRC":
            sb.table("positions").update({"is_active": False}).eq("id", p["id"]).execute()
        else:
            current_price = prices.get(ticker)
            if current_price:
                sb.table("positions").update({
                    "entry_price": current_price,
                    "entry_date": today_str,
                }).eq("id", p["id"]).execute()
    # Update both legacy settings and portfolios table
    upsert_setting("inception_date", today_str)
    sb.table("portfolios").update({"inception_date": today_str}).eq("id", portfolio_id).execute()
