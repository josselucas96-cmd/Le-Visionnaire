"""Articles Admin cockpit — CRUD + markdown editor with live preview.

Hidden from the public sidebar nav via CSS injected from other pages
(see utils/articles.hide_admin_from_nav). Reachable via a link from
the main /Admin page, or via direct URL `/Articles_Admin`.

Password-gated (same `admin_password` secret as /Admin).
"""
import streamlit as st
from streamlit_quill import st_quill

from utils import SPECULA_ICON
from utils.articles import (
    list_articles, get_article, upsert_article, delete_article,
    slugify, format_date, reading_time, upload_cover_image,
)


# Toolbar: rich formatting (fonts, sizes, colors, alignment, lists, headings,
# blockquote, code block, links, inline images, formulas) — covers everything
# the user asked for. NB: Quill has no native table support; for tables, paste
# pre-made HTML or use the link/image route.
QUILL_TOOLBAR = [
    [{"font": []}, {"size": []}],
    ["bold", "italic", "underline", "strike"],
    [{"color": []}, {"background": []}],
    [{"script": "super"}, {"script": "sub"}],
    [{"header": 1}, {"header": 2}, {"header": 3}, "blockquote", "code-block"],
    [{"list": "ordered"}, {"list": "bullet"}, {"indent": "-1"}, {"indent": "+1"}],
    [{"align": []}],
    ["link", "image", "video", "formula"],
    ["clean"],
]


st.set_page_config(
    page_title="Articles Admin | Specula",
    page_icon=SPECULA_ICON,
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Auth gate (mirror /Admin) ─────────────────────────────────────────────────
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("Articles Admin — Access")
    pwd = st.text_input("Password", type="password")
    if st.button("Login", type="primary"):
        if pwd == st.secrets.get("admin_password", ""):
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Wrong password.")
    st.stop()


# ── Styling ───────────────────────────────────────────────────────────────────
st.markdown(
    """
<style>
    [data-testid="stSidebar"] { display: none; }
    [data-testid="stHeader"] { display: none !important; }
    .block-container { padding-top: 1.5rem; padding-bottom: 2rem; max-width: 1400px; }

    /* Hide both Admin pages from each other's sidebar by hiding the whole sidebar nav */
    [data-testid="stSidebarNav"] { display: none !important; }

    .adm-title {
        font-family: "Cormorant Garamond", Georgia, serif;
        font-size: 2rem; font-weight: 700;
    }
    .adm-back {
        font-size: 0.85rem; color: #888; text-decoration: none;
    }
    .adm-back:hover { color: #00D09C; }

    .article-row {
        display: grid; grid-template-columns: 60px 1fr 100px 90px 90px;
        gap: 0.8rem; align-items: center;
        padding: 0.6rem 0.8rem; border-bottom: 1px solid rgba(255,255,255,0.06);
    }
    .article-row-img { width: 56px; height: 40px; object-fit: cover;
                       border-radius: 4px; background: #0a0e1a; }
    .article-row-title { font-weight: 600; color: #EEE; }
    .article-row-subtitle { color: #888; font-size: 0.82rem; font-style: italic; }
    .article-row-meta { color: #666; font-size: 0.78rem; }
    .badge-draft { background: #4A3500; color: #FFC857; padding: 0.15rem 0.5rem;
                   border-radius: 3px; font-size: 0.7rem; text-transform: uppercase;
                   font-weight: 700; letter-spacing: 1px; }
    .badge-published { background: #003A2A; color: #00D09C; padding: 0.15rem 0.5rem;
                       border-radius: 3px; font-size: 0.7rem; text-transform: uppercase;
                       font-weight: 700; letter-spacing: 1px; }
    .badge-featured { background: #2D1A4D; color: #C7A6FF; padding: 0.15rem 0.5rem;
                      border-radius: 3px; font-size: 0.7rem; text-transform: uppercase;
                      font-weight: 700; letter-spacing: 1px; margin-left: 0.4rem; }

    .preview-pane {
        background: #060912; border: 1px solid rgba(255,255,255,0.08);
        border-radius: 6px; padding: 1.5rem; max-height: 720px; overflow-y: auto;
    }
    .preview-pane h1 { font-family: 'Cormorant Garamond', serif !important;
                       font-size: 2rem; color: #FAFAFA; }
    .preview-pane h2 { font-family: 'Cormorant Garamond', serif !important;
                       font-size: 1.5rem; color: #FAFAFA; }
    .preview-pane p { color: #DDD; line-height: 1.7; }
</style>
""",
    unsafe_allow_html=True,
)

# ── Header + logout ───────────────────────────────────────────────────────────
hcol1, hcol2, hcol3 = st.columns([6, 2, 1])
with hcol1:
    st.markdown('<div class="adm-title">📝 Articles Admin</div>', unsafe_allow_html=True)
with hcol2:
    st.markdown(
        '<a href="/Admin" target="_self" class="adm-back">← Portfolio Admin</a>',
        unsafe_allow_html=True,
    )
with hcol3:
    if st.button("Logout", key="art_logout"):
        st.session_state.authenticated = False
        st.rerun()

st.divider()


# ── Routing via session state: list / edit ────────────────────────────────────
if "art_admin_view" not in st.session_state:
    st.session_state.art_admin_view = "list"
if "art_admin_editing_id" not in st.session_state:
    st.session_state.art_admin_editing_id = None


def go_to_list():
    st.session_state.art_admin_view = "list"
    st.session_state.art_admin_editing_id = None


def go_to_edit(article_id: int | None = None):
    st.session_state.art_admin_view = "edit"
    st.session_state.art_admin_editing_id = article_id


# ──────────────────────────────────────────────────────────────────────────────
# LIST VIEW
# ──────────────────────────────────────────────────────────────────────────────
if st.session_state.art_admin_view == "list":
    bcol1, bcol2 = st.columns([1, 5])
    with bcol1:
        if st.button("➕ New article", type="primary"):
            go_to_edit(None)
            st.rerun()
    with bcol2:
        st.caption("Tip: open `/Articles` in another tab to see the public view.")

    st.write("")

    drafts    = list_articles("draft")
    published = list_articles("published")
    archived  = list_articles("archived")

    tab1, tab2, tab3 = st.tabs([f"Published ({len(published)})", f"Drafts ({len(drafts)})", f"Archived ({len(archived)})"])

    def render_list(articles: list[dict]):
        if not articles:
            st.info("Nothing here yet.")
            return
        for a in articles:
            row_cols = st.columns([1, 4, 1, 1, 1])
            with row_cols[0]:
                cover = a.get("cover_image_url")
                if cover:
                    st.markdown(f'<img src="{cover}" class="article-row-img" />', unsafe_allow_html=True)
                else:
                    st.markdown('<div class="article-row-img"></div>', unsafe_allow_html=True)
            with row_cols[1]:
                badge = ""
                if a.get("featured"):
                    badge = '<span class="badge-featured">Featured</span>'
                st.markdown(
                    f'<div class="article-row-title">{a["title"]} {badge}</div>'
                    + (f'<div class="article-row-subtitle">{a["subtitle"]}</div>' if a.get("subtitle") else "")
                    + f'<div class="article-row-meta">{format_date(a.get("published_at") or a.get("updated_at"))}  ·  {reading_time(a.get("body", ""))}  ·  slug: <code>{a["slug"]}</code></div>',
                    unsafe_allow_html=True,
                )
            with row_cols[2]:
                if st.button("Edit", key=f"edit_{a['id']}"):
                    go_to_edit(a["id"])
                    st.rerun()
            with row_cols[3]:
                # Quick public-view link
                st.markdown(
                    f'<a href="/Articles?slug={a["slug"]}" target="_blank" '
                    f'style="font-size:0.85rem; color:#888;">↗ View</a>',
                    unsafe_allow_html=True,
                )
            with row_cols[4]:
                # 2-step delete: 1st click arms, 2nd click executes. Auto-disarms
                # on the next rerun if the user navigates away.
                confirm_key = f"art_list_del_confirm_{a['id']}"
                if not st.session_state.get(confirm_key):
                    if st.button("🗑️", key=f"del_{a['id']}", help="Click to delete (will ask to confirm)"):
                        st.session_state[confirm_key] = True
                        st.rerun()
                else:
                    if st.button("✅ Confirm", key=f"del_yes_{a['id']}", help="Confirm permanent delete"):
                        delete_article(a["id"])
                        st.session_state.pop(confirm_key, None)
                        st.success(f"Deleted '{a['title']}'.")
                        st.rerun()
                    if st.button("Cancel", key=f"del_no_{a['id']}"):
                        st.session_state.pop(confirm_key, None)
                        st.rerun()
            st.write("")

    with tab1: render_list(published)
    with tab2: render_list(drafts)
    with tab3: render_list(archived)


# ──────────────────────────────────────────────────────────────────────────────
# EDIT VIEW
# ──────────────────────────────────────────────────────────────────────────────
elif st.session_state.art_admin_view == "edit":
    if st.button("← Back to list"):
        go_to_list()
        st.rerun()

    editing_id = st.session_state.art_admin_editing_id
    existing = get_article("") if not editing_id else None  # always None for new
    if editing_id:
        all_articles = list_articles(status="")  # status="" disabled the filter
        # Need a way to fetch by id — refetch all and find
        from utils.data import get_client
        sb = get_client()
        rows = sb.table("articles").select("*").eq("id", editing_id).execute().data
        existing = rows[0] if rows else None
        if not existing:
            st.error(f"Article id={editing_id} not found.")
            go_to_list()
            st.rerun()

    is_new = existing is None
    st.subheader("New article" if is_new else f"Editing: {existing['title']}")

    # ── Form fields ──
    col1, col2 = st.columns(2)
    with col1:
        title = st.text_input(
            "Title",
            value=existing["title"] if existing else "",
            key="art_title",
        )
    with col2:
        # Slug — auto-suggested from title, editable
        default_slug = (existing["slug"] if existing else slugify(title))
        slug = st.text_input(
            "Slug (URL-friendly, unique)",
            value=default_slug,
            key="art_slug",
            help="Auto-generated from title. Edit if you want a custom URL.",
        )

    subtitle = st.text_input(
        "Subtitle (optional, italic accroche)",
        value=existing.get("subtitle") if existing else "",
        key="art_subtitle",
    )

    # ── Cover image: upload or URL ──
    cic1, cic2 = st.columns([1, 1])
    with cic1:
        st.caption("Cover image")
        uploaded = st.file_uploader(
            "Upload an image",
            type=["jpg", "jpeg", "png", "webp", "gif"],
            key="art_cover_upload",
        )
        if uploaded is not None:
            mime = uploaded.type or "image/jpeg"
            with st.spinner("Uploading to Supabase Storage..."):
                url = upload_cover_image(uploaded.read(), uploaded.name, mime)
            if url:
                st.session_state["art_cover_url_input"] = url
                st.success("Uploaded.")
    with cic2:
        # Use session_state to keep the URL across reruns / after upload
        initial_url = ""
        if existing and existing.get("cover_image_url"):
            initial_url = existing["cover_image_url"]
        if "art_cover_url_input" not in st.session_state:
            st.session_state["art_cover_url_input"] = initial_url
        cover_url = st.text_input(
            "Image URL (or paste a URL from Imgur etc.)",
            key="art_cover_url_input",
        )
        if cover_url:
            st.markdown(
                f'<img src="{cover_url}" style="max-width:100%; max-height:180px; '
                f'border-radius:6px;" />',
                unsafe_allow_html=True,
            )

    # ── Status + featured ──
    sc1, sc2, sc3 = st.columns([1, 1, 1])
    with sc1:
        status = st.selectbox(
            "Status",
            ["draft", "published", "archived"],
            index=["draft", "published", "archived"].index(
                existing["status"] if existing else "draft"
            ),
            key="art_status",
        )
    with sc2:
        featured = st.toggle(
            "Featured (only 1 at a time)",
            value=bool(existing.get("featured")) if existing else False,
            key="art_featured",
        )
    with sc3:
        if existing and existing.get("published_at"):
            st.caption(f"Originally published: {format_date(existing['published_at'])}")

    # ── WYSIWYG editor (Quill) ──
    # Editor IS the preview — what you see is what gets rendered on /Articles.
    # Body is stored as HTML, rendered via st.markdown(unsafe_allow_html=True).
    st.write("")
    st.markdown("**Body** — use the toolbar to format. Drag-resize images after insertion.")
    body = st_quill(
        value=existing["body"] if existing else "",
        placeholder="Start writing your article…",
        html=True,
        toolbar=QUILL_TOOLBAR,
        key=f"art_body_quill_{editing_id or 'new'}",
    )
    if body is None:
        body = ""

    # ── Reading time hint (strip HTML tags for accurate word count) ──
    if body:
        import re as _re
        plain = _re.sub(r"<[^>]+>", " ", body)
        word_count = len(plain.split())
        st.caption(f"Estimated reading time: ~{max(1, round(word_count / 250))} min read · {word_count} words")

    st.write("")

    # ── Action buttons ──
    # "Save" alone — status is driven entirely by the dropdown above.
    # Delete uses a 2-step confirm to prevent misclicks.
    bcol1, bcol2, bcol3 = st.columns([1, 1, 4])
    with bcol1:
        save_clicked = st.button("💾 Save", type="primary")
    with bcol2:
        if existing:
            confirm_key = f"art_del_confirm_{existing['id']}"
            if not st.session_state.get(confirm_key):
                if st.button("🗑️ Delete", help="Click again to confirm"):
                    st.session_state[confirm_key] = True
                    st.rerun()
            else:
                st.warning("Click 'Confirm delete' to permanently remove this article.")
                cc1, cc2 = st.columns(2)
                with cc1:
                    if st.button("✅ Confirm delete", type="primary", key=f"art_del_yes_{existing['id']}"):
                        delete_article(existing["id"])
                        st.session_state.pop(confirm_key, None)
                        st.success(f"Deleted '{existing['title']}'.")
                        go_to_list()
                        st.rerun()
                with cc2:
                    if st.button("Cancel", key=f"art_del_no_{existing['id']}"):
                        st.session_state.pop(confirm_key, None)
                        st.rerun()

    if save_clicked:
        if not title or not slug or not body:
            st.error("Title, slug and body are required.")
        else:
            from datetime import datetime, timezone
            data = {
                "slug":            slug,
                "title":           title,
                "subtitle":        subtitle or None,
                "cover_image_url": cover_url or None,
                "body":            body,
                "status":          status,
                "featured":        featured,
            }
            if existing:
                data["id"] = existing["id"]
            # Auto-set published_at the first time the article goes published.
            if status == "published":
                if not (existing and existing.get("published_at")):
                    data["published_at"] = datetime.now(timezone.utc).isoformat()
                else:
                    data["published_at"] = existing["published_at"]

            try:
                saved = upsert_article(data)
                if is_new:
                    st.session_state.pop("art_cover_url_input", None)
                st.success(f"{'Created' if is_new else 'Updated'} '{saved.get('title', title)}'.")
                if status == "published":
                    st.markdown(
                        f'✅ View it live: <a href="/Articles?slug={slug}" target="_blank">/Articles?slug={slug}</a>',
                        unsafe_allow_html=True,
                    )
                go_to_list()
                st.rerun()
            except Exception as e:
                st.error(f"Save failed: {e}")
