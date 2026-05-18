"""Articles CRUD + helpers for the Articles page (public + admin).

Articles live in the Supabase `articles` table:
    id, slug, title, subtitle, cover_image_url, body, status,
    featured, published_at, created_at, updated_at

Used by:
- pages/Articles.py        (public list + detail)
- pages/Articles_Admin.py  (admin CRUD + markdown editor)
"""
import re
from datetime import datetime, timezone

import streamlit as st

from utils.data import get_client


@st.cache_data(ttl=60)
def list_articles(status: str = "published") -> list[dict]:
    """Return all articles with given status, ordered by published_at DESC."""
    sb = get_client()
    q = (
        sb.table("articles")
        .select("*")
        .order("published_at", desc=True)
    )
    if status:
        q = q.eq("status", status)
    try:
        return q.execute().data or []
    except Exception:
        return []


@st.cache_data(ttl=60)
def get_article(slug: str) -> dict | None:
    """Fetch a single article by slug."""
    sb = get_client()
    try:
        rows = sb.table("articles").select("*").eq("slug", slug).limit(1).execute().data
        return rows[0] if rows else None
    except Exception:
        return None


def get_featured_article(articles: list[dict] | None = None) -> dict | None:
    """Return the most recent published article with featured=True, or None."""
    if articles is None:
        articles = list_articles("published")
    feats = [a for a in articles if a.get("featured")]
    return feats[0] if feats else None


def upsert_article(data: dict) -> dict:
    """Create or update an article. Returns the saved row."""
    sb = get_client()
    data = {**data, "updated_at": datetime.now(timezone.utc).isoformat()}

    # Enforce "only one featured" — if this article is being set featured,
    # un-feature all others.
    if data.get("featured"):
        try:
            sb.table("articles").update({"featured": False}).neq(
                "id", data.get("id") or -1
            ).execute()
        except Exception:
            pass

    if data.get("id"):
        res = sb.table("articles").update(data).eq("id", data["id"]).execute()
    else:
        res = sb.table("articles").insert(data).execute()
    list_articles.clear()
    get_article.clear()
    return res.data[0] if res.data else data


def delete_article(article_id: int) -> None:
    sb = get_client()
    sb.table("articles").delete().eq("id", article_id).execute()
    list_articles.clear()
    get_article.clear()


def slugify(text: str) -> str:
    """Generate a URL-safe slug from a title."""
    text = (text or "").lower()
    # Replace accented chars with ASCII (basic mapping)
    import unicodedata
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    # Keep alphanumeric + space + dash
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    text = text.strip("-")
    return text[:80] or "untitled"


def reading_time(body: str) -> str:
    """Estimate reading time in minutes (~250 wpm).

    Strips HTML tags first since Quill stores HTML — without stripping,
    every `<p>` and `</p>` would inflate the word count.
    """
    plain = re.sub(r"<[^>]+>", " ", body or "")
    words = len(plain.split())
    minutes = max(1, round(words / 250))
    return f"{minutes} min read"


def format_date(iso_str: str | None) -> str:
    """Format an ISO timestamp as e.g. 'May 19, 2026'."""
    if not iso_str:
        return ""
    try:
        # Handle both with and without timezone
        s = iso_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        return dt.strftime("%b %d, %Y")
    except Exception:
        return iso_str[:10]


def upload_cover_image(file_bytes: bytes, filename: str, content_type: str = "image/jpeg") -> str | None:
    """Upload a cover image to Supabase Storage bucket `article-images`.

    Returns the public URL on success, None on failure. The bucket must be
    created manually (Supabase Dashboard → Storage → New bucket, public).
    Anon writes require the `anon_article_images_all` policy.
    """
    sb = get_client()
    # Make filename unique by timestamping it
    import uuid
    ext = filename.rsplit(".", 1)[-1] if "." in filename else "jpg"
    safe_name = f"cover-{uuid.uuid4().hex[:12]}.{ext}"
    try:
        sb.storage.from_("article-images").upload(
            path=safe_name,
            file=file_bytes,
            file_options={"content-type": content_type, "upsert": "true"},
        )
        return sb.storage.from_("article-images").get_public_url(safe_name)
    except Exception as e:
        st.error(f"Upload failed: {e}")
        return None


def hide_admin_from_nav():
    """CSS hack to hide Articles_Admin from the Streamlit sidebar nav.

    Call this from every PUBLIC page so visitors don't see the admin link.
    The Admin pages themselves don't need to call this (they're behind auth).
    """
    st.markdown(
        """
        <style>
        [data-testid="stSidebarNav"] li:has(a[href*="Articles_Admin"]) { display: none !important; }
        [data-testid="stSidebarNav"] li:has(a[href*="Articles_admin"]) { display: none !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )
