import streamlit as st
from utils.data import get_client


@st.cache_data(ttl=300)
def get_research(status_filter=None):
    sb = get_client()
    query = sb.table("research").select("*").order("published_at", desc=True)
    if status_filter:
        query = query.eq("status", status_filter)
    return query.execute().data


def upsert_research(data: dict):
    sb = get_client()
    if "id" in data and data["id"]:
        sb.table("research").update(data).eq("id", data["id"]).execute()
    else:
        data.pop("id", None)
        sb.table("research").insert(data).execute()


def delete_research(research_id: int):
    sb = get_client()
    sb.table("research").delete().eq("id", research_id).execute()


def upload_pdf(file_bytes: bytes, filename: str) -> str:
    sb = get_client()
    path = filename
    sb.storage.from_("research-docs").upload(
        path, file_bytes, {"content-type": "application/pdf", "upsert": "true"}
    )
    return sb.storage.from_("research-docs").get_public_url(path)
