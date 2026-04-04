import streamlit as st
from supabase import create_client


@st.cache_resource
def get_client():
    return create_client(st.secrets["supabase_url"], st.secrets["supabase_key"])


def get_positions(active_only=True):
    sb = get_client()
    query = sb.table("positions").select("*")
    if active_only:
        query = query.eq("is_active", True)
    return query.order("ticker").execute().data


def get_transactions():
    sb = get_client()
    return sb.table("transactions").select("*").order("date", desc=True).execute().data


def get_setting(key, default=None):
    sb = get_client()
    result = sb.table("settings").select("value").eq("key", key).execute().data
    return result[0]["value"] if result else default


def upsert_setting(key, value):
    sb = get_client()
    sb.table("settings").upsert({"key": key, "value": str(value)}).execute()


def add_position(data: dict):
    sb = get_client()
    existing = (
        sb.table("positions")
        .select("id, weight, entry_price")
        .eq("ticker", data["ticker"])
        .eq("is_active", True)
        .execute()
        .data
    )
    if existing:
        ex = existing[0]
        old_w  = float(ex["weight"])
        new_w  = float(data["weight"])
        total_w = old_w + new_w
        pru = round((old_w * float(ex["entry_price"]) + new_w * float(data["entry_price"])) / total_w, 4)
        update_data = {"weight": total_w, "entry_price": pru}
        # Only update thesis if a new one was explicitly provided
        new_thesis = (data.get("thesis_short") or "").strip()
        if new_thesis:
            update_data["thesis_short"] = new_thesis
        # name, sector, geography, thematic: always keep existing
        sb.table("positions").update(update_data).eq("id", ex["id"]).execute()
        sb.table("transactions").insert({
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
    perf = round((out_price - pos_out["entry_price"]) / pos_out["entry_price"] * 100, 2)
    sb.table("transactions").insert({
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
    sb.table("positions").insert(in_data).execute()
