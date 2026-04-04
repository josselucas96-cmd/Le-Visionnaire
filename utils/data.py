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
    sb.table("positions").insert(data).execute()


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
        "ticker_in": in_data["ticker"],
        "price_in": in_data["entry_price"],
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
