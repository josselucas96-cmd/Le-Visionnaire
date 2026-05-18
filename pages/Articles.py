"""Public Articles page.

Two views in one file, switched by `?slug=...` query param:
1. No slug: home view with featured article + grid of others
2. With slug: full article detail view

Articles are read from Supabase `articles` table (status='published').
"""
import streamlit as st

from utils import SPECULA_ICON
from utils.nav import render_nav
from utils.articles import (
    list_articles, get_article, get_featured_article,
    reading_time, format_date, hide_admin_from_nav,
)


st.set_page_config(
    page_title="Articles | Specula",
    page_icon=SPECULA_ICON,
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Theme + sidebar/admin hidden ──────────────────────────────────────────────
hide_admin_from_nav()

st.markdown(
    """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@600;700&display=swap');

    [data-testid="stSidebar"] { display: none; }
    .block-container { padding-top: 4rem; padding-bottom: 3rem; max-width: 1200px; }

    .articles-eyebrow {
        font-size: 0.7rem; font-weight: 700; letter-spacing: 2px;
        color: #00D09C; text-transform: uppercase; margin-bottom: 0.4rem;
    }
    .articles-h1 {
        font-family: "Cormorant Garamond", Georgia, serif !important;
        font-size: 3rem; font-weight: 700; letter-spacing: -1px;
        margin-bottom: 0.4rem; line-height: 1.05; color: #FAFAFA;
    }
    .articles-tagline {
        color: #888; font-size: 0.95rem; margin-bottom: 2.5rem;
    }

    /* Featured (hero) card */
    .featured-card {
        display: grid; grid-template-columns: 1.4fr 1fr; gap: 2.5rem;
        background: linear-gradient(180deg, rgba(0,208,156,0.04) 0%, rgba(0,0,0,0) 60%);
        border: 1px solid rgba(255,255,255,0.06);
        border-radius: 14px;
        padding: 1.5rem;
        margin-bottom: 3rem;
        text-decoration: none !important;
    }
    .featured-card:hover { border-color: rgba(0,208,156,0.3); }
    .featured-img {
        width: 100%; height: 100%; min-height: 300px; max-height: 460px;
        object-fit: cover; border-radius: 8px; background: #111;
    }
    .featured-img-placeholder {
        width: 100%; min-height: 300px; max-height: 460px;
        background: linear-gradient(135deg, #0a0e1a 0%, #1a2030 100%);
        border-radius: 8px; display: flex; align-items: center; justify-content: center;
        color: #2a3550; font-family: "Cormorant Garamond", serif; font-size: 4rem;
    }
    .featured-text { padding: 1.2rem 0.5rem; display: flex; flex-direction: column; justify-content: center; }
    .featured-label {
        font-size: 0.65rem; font-weight: 700; letter-spacing: 2.5px;
        color: #00D09C; text-transform: uppercase; margin-bottom: 0.8rem;
    }
    .featured-title {
        font-family: "Cormorant Garamond", Georgia, serif !important;
        font-size: 2.4rem; font-weight: 700; letter-spacing: -0.5px;
        line-height: 1.15; color: #FAFAFA; margin-bottom: 0.6rem;
    }
    .featured-subtitle {
        font-style: italic; color: #BBB; font-size: 1.05rem; line-height: 1.5;
        margin-bottom: 1.2rem;
    }
    .featured-meta { color: #666; font-size: 0.82rem; }

    /* Section heading */
    .section-heading {
        font-size: 0.75rem; font-weight: 700; letter-spacing: 2px;
        color: #888; text-transform: uppercase;
        border-top: 1px solid rgba(255,255,255,0.08);
        padding-top: 1.5rem; margin-top: 1rem; margin-bottom: 1.5rem;
    }

    /* Grid card */
    .grid-card {
        display: block;
        background: rgba(255,255,255,0.02);
        border: 1px solid rgba(255,255,255,0.06);
        border-radius: 10px;
        overflow: hidden;
        text-decoration: none !important;
        transition: border-color 0.15s, transform 0.15s;
        height: 100%;
    }
    .grid-card:hover { border-color: rgba(0,208,156,0.3); transform: translateY(-2px); }
    .grid-card-img {
        width: 100%; height: 180px; object-fit: cover; background: #0a0e1a;
        display: block;
    }
    .grid-card-img-placeholder {
        width: 100%; height: 180px;
        background: linear-gradient(135deg, #0a0e1a 0%, #1a2030 100%);
        display: flex; align-items: center; justify-content: center;
        color: #2a3550; font-family: "Cormorant Garamond", serif; font-size: 2.5rem;
    }
    .grid-card-body { padding: 1rem 1.1rem 1.2rem; }
    .grid-card-title {
        font-family: "Cormorant Garamond", Georgia, serif !important;
        font-size: 1.35rem; font-weight: 700; line-height: 1.2;
        color: #FAFAFA; margin-bottom: 0.4rem;
    }
    .grid-card-subtitle { color: #999; font-size: 0.85rem; line-height: 1.4; margin-bottom: 0.6rem; font-style: italic; }
    .grid-card-meta { color: #666; font-size: 0.72rem; }

    /* ─── Article detail ─── */
    .article-back {
        font-size: 0.85rem; color: #888; text-decoration: none;
        display: inline-block; margin-bottom: 1.5rem;
    }
    .article-back:hover { color: #00D09C; }
    .article-eyebrow {
        font-size: 0.65rem; font-weight: 700; letter-spacing: 2.5px;
        color: #00D09C; text-transform: uppercase; margin-bottom: 0.6rem;
    }
    .article-title {
        font-family: "Cormorant Garamond", Georgia, serif !important;
        font-size: 3.4rem; font-weight: 700; letter-spacing: -1px;
        line-height: 1.05; color: #FAFAFA; margin-bottom: 0.6rem;
    }
    .article-subtitle {
        font-style: italic; color: #BBB; font-size: 1.25rem;
        line-height: 1.5; margin-bottom: 1.5rem;
    }
    .article-meta {
        color: #666; font-size: 0.85rem; margin-bottom: 2rem;
        padding-bottom: 1.2rem; border-bottom: 1px solid rgba(255,255,255,0.08);
    }
    .article-cover {
        width: 100%; max-height: 480px; object-fit: cover;
        border-radius: 8px; margin: 1rem 0 2.5rem; background: #0a0e1a;
    }
    .article-body {
        max-width: 720px; margin: 0 auto; color: #DDD;
        font-size: 1.05rem; line-height: 1.85;
    }
    .article-body h1 {
        font-family: "Cormorant Garamond", Georgia, serif !important;
        font-size: 2.2rem; font-weight: 700; margin-top: 2.5rem; margin-bottom: 1rem;
        color: #FAFAFA;
    }
    .article-body h2 {
        font-family: "Cormorant Garamond", Georgia, serif !important;
        font-size: 1.7rem; font-weight: 700; margin-top: 2rem; margin-bottom: 0.8rem;
        color: #FAFAFA;
    }
    .article-body h3 {
        font-size: 1.25rem; font-weight: 700; margin-top: 1.5rem; margin-bottom: 0.6rem;
        color: #EEE;
    }
    .article-body p { margin-bottom: 1.3rem; }
    .article-body blockquote {
        border-left: 3px solid #00D09C; padding-left: 1.2rem; margin: 1.5rem 0;
        color: #AAA; font-style: italic;
    }
    .article-body code {
        background: rgba(255,255,255,0.06); padding: 0.15rem 0.4rem;
        border-radius: 3px; font-size: 0.9em; color: #FFC857;
    }
    .article-body pre {
        background: #0a0e1a; padding: 1rem; border-radius: 6px; overflow-x: auto;
        border: 1px solid rgba(255,255,255,0.06); margin: 1.2rem 0;
    }
    .article-body pre code { background: transparent; padding: 0; color: #DDD; }
    .article-body table {
        width: 100%; border-collapse: collapse; margin: 1.5rem 0;
    }
    .article-body th, .article-body td {
        border-bottom: 1px solid rgba(255,255,255,0.08);
        padding: 0.6rem 0.8rem; text-align: left;
    }
    .article-body th { color: #00D09C; font-size: 0.85rem;
                       text-transform: uppercase; letter-spacing: 1px; }
    .article-body img { max-width: 100%; border-radius: 6px; margin: 1.2rem 0; }
    .article-body a { color: #00D09C; text-decoration: underline; }
    .article-body ul, .article-body ol { margin: 0.8rem 0 1.3rem 1.5rem; }
    .article-body li { margin-bottom: 0.4rem; }

    /* ── Quill class mappings ──
       Quill stores formatting as CSS classes (ql-size-large, ql-font-serif,
       ql-align-center, ql-indent-N). Those classes live inside Quill's CSS
       which is only loaded in the editor — we have to re-declare them here
       so the public page renders matching styles. */
    .article-body .ql-size-small  { font-size: 0.75em; }
    .article-body .ql-size-large  { font-size: 1.5em; line-height: 1.5; }
    .article-body .ql-size-huge   { font-size: 2.5em; line-height: 1.3; }
    .article-body .ql-font-serif      { font-family: Georgia, "Times New Roman", serif; }
    .article-body .ql-font-monospace  { font-family: "Courier New", monospace; }
    .article-body .ql-align-center  { text-align: center; }
    .article-body .ql-align-right   { text-align: right; }
    .article-body .ql-align-justify { text-align: justify; }
    .article-body .ql-indent-1 { padding-left: 3em; }
    .article-body .ql-indent-2 { padding-left: 6em; }
    .article-body .ql-indent-3 { padding-left: 9em; }
    .article-body .ql-indent-4 { padding-left: 12em; }
    .article-body .ql-indent-5 { padding-left: 15em; }
    .article-body .ql-indent-6 { padding-left: 18em; }
    .article-body .ql-indent-7 { padding-left: 21em; }
    .article-body .ql-indent-8 { padding-left: 24em; }

    .disclaimer-articles {
        font-size: 0.72rem; color: #444; margin-top: 3rem;
        border-top: 1px solid #1A1F26; padding-top: 1rem; line-height: 1.5;
        max-width: 720px; margin-left: auto; margin-right: auto;
    }
</style>
""",
    unsafe_allow_html=True,
)

render_nav("articles")
st.write("")

# ── Routing: ?slug=X means detail view, otherwise home ────────────────────────
qp = st.query_params
slug = qp.get("slug")


def card_image(url: str | None, placeholder_char: str = "S", css_class: str = "grid-card-img") -> str:
    if url:
        return f'<img src="{url}" class="{css_class}" />'
    placeholder_class = css_class + "-placeholder"
    return f'<div class="{placeholder_class}">{placeholder_char}</div>'


def card_html(article: dict) -> str:
    url = f"/Articles?slug={article['slug']}"
    cover = article.get("cover_image_url")
    initial = (article.get("title", "?")[:1]).upper()
    return (
        f'<a href="{url}" target="_self" class="grid-card">'
        f'{card_image(cover, initial, "grid-card-img")}'
        f'<div class="grid-card-body">'
        f'<div class="grid-card-title">{article.get("title", "Untitled")}</div>'
        + (f'<div class="grid-card-subtitle">{article["subtitle"]}</div>' if article.get("subtitle") else "")
        + f'<div class="grid-card-meta">{format_date(article.get("published_at"))}  ·  {reading_time(article.get("body", ""))}</div>'
        f'</div>'
        f'</a>'
    )


# ──────────────────────────────────────────────────────────────────────────────
# DETAIL VIEW
# ──────────────────────────────────────────────────────────────────────────────
if slug:
    article = get_article(slug)
    if not article or article.get("status") != "published":
        st.markdown('<a href="/Articles" target="_self" class="article-back">← Back to articles</a>', unsafe_allow_html=True)
        st.markdown('<div class="articles-h1">Article not found</div>', unsafe_allow_html=True)
        st.markdown('<div class="articles-tagline">This article may have been moved or unpublished.</div>', unsafe_allow_html=True)
    else:
        st.markdown('<a href="/Articles" target="_self" class="article-back">← Back to articles</a>', unsafe_allow_html=True)

        # Header (title + subtitle + meta)
        st.markdown('<div class="article-eyebrow">Article</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="article-title">{article["title"]}</div>', unsafe_allow_html=True)
        if article.get("subtitle"):
            st.markdown(f'<div class="article-subtitle">{article["subtitle"]}</div>', unsafe_allow_html=True)
        meta_parts = ["By Lucas Josse"]
        if article.get("published_at"):
            meta_parts.append(format_date(article["published_at"]))
        meta_parts.append(reading_time(article.get("body", "")))
        st.markdown(f'<div class="article-meta">{"  ·  ".join(meta_parts)}</div>', unsafe_allow_html=True)

        # Cover image
        if article.get("cover_image_url"):
            st.markdown(f'<img src="{article["cover_image_url"]}" class="article-cover" />', unsafe_allow_html=True)

        # Body — Quill stores HTML; render inside the styled .article-body wrapper.
        # Single call so the wrapping div actually contains the body (otherwise
        # Streamlit treats each markdown call as its own DOM block).
        st.markdown(
            f'<div class="article-body">{article["body"]}</div>',
            unsafe_allow_html=True,
        )

        # You might also like
        all_articles = [a for a in list_articles("published") if a["id"] != article["id"]]
        if all_articles:
            st.markdown('<div class="section-heading" style="max-width: 720px; margin: 3rem auto 1.5rem;">You might also like</div>', unsafe_allow_html=True)
            cols = st.columns(min(3, len(all_articles)))
            for col, a in zip(cols, all_articles[:3]):
                with col:
                    st.markdown(card_html(a), unsafe_allow_html=True)

    st.markdown(
        """<div class="disclaimer-articles">
        These articles reflect personal opinions for educational and informational purposes only.
        They do not constitute investment advice. The author may hold positions in securities mentioned.
        </div>""",
        unsafe_allow_html=True,
    )
    st.stop()


# ──────────────────────────────────────────────────────────────────────────────
# HOME VIEW (no slug)
# ──────────────────────────────────────────────────────────────────────────────
all_articles = list_articles("published")

st.markdown('<div class="articles-eyebrow">Specula</div>', unsafe_allow_html=True)
st.markdown('<div class="articles-h1">Articles</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="articles-tagline">Thoughts on capital allocation, market structure, '
    'and individual companies — written for sophisticated investors.</div>',
    unsafe_allow_html=True,
)

if not all_articles:
    st.info("No articles published yet. Check back soon.")
    st.stop()

# Featured article (hero)
featured = get_featured_article(all_articles)
others = [a for a in all_articles if not featured or a["id"] != featured["id"]]

if featured:
    cover = featured.get("cover_image_url")
    initial = (featured.get("title", "S")[:1]).upper()
    href = f'/Articles?slug={featured["slug"]}'
    image_html = (
        f'<img src="{cover}" class="featured-img" />' if cover
        else f'<div class="featured-img-placeholder">{initial}</div>'
    )
    subtitle_html = f'<div class="featured-subtitle">{featured["subtitle"]}</div>' if featured.get("subtitle") else ""
    meta = f'{format_date(featured.get("published_at"))}  ·  {reading_time(featured.get("body", ""))}'
    st.markdown(
        f'<a href="{href}" target="_self" class="featured-card">'
        f'<div>{image_html}</div>'
        f'<div class="featured-text">'
        f'<div class="featured-label">Featured</div>'
        f'<div class="featured-title">{featured["title"]}</div>'
        f'{subtitle_html}'
        f'<div class="featured-meta">{meta}</div>'
        f'</div>'
        f'</a>',
        unsafe_allow_html=True,
    )

# Grid of other articles
if others:
    st.markdown('<div class="section-heading">All Articles</div>', unsafe_allow_html=True)
    # 3 columns grid
    for i in range(0, len(others), 3):
        row = others[i:i + 3]
        cols = st.columns(3)
        for col, a in zip(cols, row):
            with col:
                st.markdown(card_html(a), unsafe_allow_html=True)

st.markdown(
    """<div class="disclaimer-articles">
    These articles reflect personal opinions for educational and informational purposes only.
    They do not constitute investment advice. The author may hold positions in securities mentioned.
    </div>""",
    unsafe_allow_html=True,
)
