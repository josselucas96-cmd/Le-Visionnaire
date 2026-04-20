import streamlit as st
from utils.nav import render_nav

st.set_page_config(
    page_title="Specula — The Speculative Thesis",
    page_icon="🔭",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
    [data-testid="stSidebar"] { display: none; }
    .block-container { padding-top: 3.5rem; padding-bottom: 0; max-width: 1100px; }

    /* ── Hero ── */
    .specula-hero {
        text-align: center;
        padding: 5rem 2rem 3.5rem 2rem;
    }
    .specula-eyebrow {
        font-size: 0.72rem;
        font-weight: 700;
        letter-spacing: 4px;
        color: #4B5563;
        text-transform: uppercase;
        margin-bottom: 1.4rem;
    }
    .specula-title {
        font-family: 'Cormorant Garamond', Georgia, serif !important;
        font-size: 5rem;
        font-weight: 700;
        letter-spacing: -2px;
        line-height: 1;
        color: #F9FAFB;
        margin-bottom: 1.2rem;
    }
    .specula-tagline {
        font-size: 1.05rem;
        color: #6B7280;
        max-width: 560px;
        margin: 0 auto 2.8rem auto;
        line-height: 1.75;
        font-style: italic;
    }
    .specula-divider {
        width: 48px;
        height: 2px;
        background: linear-gradient(90deg, #6366F1, #F97316);
        margin: 0 auto 3.5rem auto;
        border-radius: 2px;
    }

    /* ── Philosophy ── */
    .philosophy-block {
        max-width: 720px;
        margin: 0 auto 5rem auto;
        text-align: center;
    }
    .philosophy-label {
        font-size: 0.68rem;
        font-weight: 700;
        letter-spacing: 3px;
        color: #374151;
        text-transform: uppercase;
        margin-bottom: 1.2rem;
    }
    .philosophy-text {
        font-size: 1.05rem;
        color: #9CA3AF;
        line-height: 1.85;
    }
    .philosophy-text b {
        color: #E5E7EB;
        font-weight: 600;
    }

    /* ── Section title ── */
    .section-label {
        font-size: 0.68rem;
        font-weight: 700;
        letter-spacing: 3px;
        color: #374151;
        text-transform: uppercase;
        text-align: center;
        margin-bottom: 2.2rem;
    }

    /* ── Portfolio cards ── */
    .portfolios-grid {
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 1.2rem;
        margin-bottom: 5rem;
    }
    .portfolio-card {
        background: #0D1117;
        border: 1px solid #1F2937;
        border-radius: 16px;
        padding: 2rem 1.8rem 1.8rem 1.8rem;
        position: relative;
        overflow: hidden;
        transition: border-color 0.2s, transform 0.2s;
        display: flex;
        flex-direction: column;
    }
    .portfolio-card:hover {
        transform: translateY(-3px);
    }
    .portfolio-card-active {
        border-color: #312E81;
        cursor: pointer;
    }
    .portfolio-card-active:hover {
        border-color: #4338CA;
    }
    .portfolio-card-soon {
        opacity: 0.6;
        cursor: default;
    }
    .card-glow {
        position: absolute;
        top: -80px; right: -80px;
        width: 200px; height: 200px;
        border-radius: 50%;
        filter: blur(60px);
        opacity: 0.12;
    }
    .card-accent {
        width: 36px;
        height: 3px;
        border-radius: 2px;
        margin-bottom: 1.4rem;
    }
    .card-number {
        font-size: 0.65rem;
        font-weight: 700;
        letter-spacing: 2px;
        margin-bottom: 0.5rem;
    }
    .card-name {
        font-family: 'Cormorant Garamond', Georgia, serif !important;
        font-size: 1.8rem;
        font-weight: 700;
        letter-spacing: -0.5px;
        color: #F9FAFB;
        margin-bottom: 0.4rem;
        line-height: 1.1;
    }
    .card-subtitle {
        font-size: 0.78rem;
        color: #6B7280;
        margin-bottom: 1.2rem;
        letter-spacing: 0.3px;
    }
    .card-description {
        font-size: 0.88rem;
        color: #6B7280;
        line-height: 1.7;
        flex: 1;
        margin-bottom: 1.4rem;
    }
    .card-badge-active {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        font-size: 0.68rem;
        font-weight: 700;
        letter-spacing: 1px;
        text-transform: uppercase;
        padding: 4px 12px;
        border-radius: 20px;
        align-self: flex-start;
    }
    .badge-live {
        background: rgba(99, 102, 241, 0.15);
        color: #818CF8;
        border: 1px solid rgba(99, 102, 241, 0.3);
    }
    .badge-soon {
        background: rgba(75, 85, 99, 0.2);
        color: #6B7280;
        border: 1px solid rgba(75, 85, 99, 0.3);
    }
    .card-cta {
        display: inline-block;
        margin-top: 1rem;
        font-size: 0.8rem;
        font-weight: 600;
        color: #818CF8;
        text-decoration: none;
        letter-spacing: 0.3px;
    }
    .card-cta:hover { color: #A5B4FC; }

    /* ── Research teaser ── */
    .research-teaser {
        background: #0D1117;
        border: 1px solid #1F2937;
        border-radius: 16px;
        padding: 2.5rem 3rem;
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 2rem;
        margin-bottom: 4rem;
    }
    .teaser-left {}
    .teaser-label {
        font-size: 0.68rem;
        font-weight: 700;
        letter-spacing: 3px;
        color: #374151;
        text-transform: uppercase;
        margin-bottom: 0.6rem;
    }
    .teaser-title {
        font-size: 1.4rem;
        font-weight: 700;
        color: #F9FAFB;
        margin-bottom: 0.5rem;
    }
    .teaser-sub {
        font-size: 0.88rem;
        color: #6B7280;
        line-height: 1.65;
        max-width: 480px;
    }
    .teaser-cta {
        display: inline-block;
        background: #111827;
        border: 1px solid #374151;
        color: #D1D5DB;
        font-size: 0.82rem;
        font-weight: 600;
        padding: 0.65rem 1.6rem;
        border-radius: 8px;
        text-decoration: none;
        white-space: nowrap;
        transition: border-color 0.15s, color 0.15s;
        flex-shrink: 0;
    }
    .teaser-cta:hover {
        border-color: #6B7280;
        color: #F9FAFB;
    }

    /* ── Footer ── */
    .specula-footer {
        text-align: center;
        padding: 2rem 0 3rem 0;
        border-top: 1px solid #111827;
    }
    .footer-logo {
        font-family: 'Cormorant Garamond', Georgia, serif !important;
        font-size: 1.2rem;
        font-weight: 700;
        color: #374151;
        margin-bottom: 0.5rem;
    }
    .footer-text {
        font-size: 0.72rem;
        color: #374151;
        line-height: 1.6;
    }
</style>
""", unsafe_allow_html=True)

render_nav("specula")

# ── Hero ──────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="specula-hero">
    <div class="specula-eyebrow">Open Research Platform</div>
    <div class="specula-title">Specula</div>
    <div class="specula-tagline">
        To observe from a high vantage point. To speculate before the consensus forms.<br>
        Three portfolios. Three convictions. Everything in real time.
    </div>
    <div class="specula-divider"></div>
</div>
""", unsafe_allow_html=True)

# ── Philosophy ────────────────────────────────────────────────────────────────
st.markdown("""
<div class="philosophy-block">
    <div class="philosophy-label">Investment Philosophy</div>
    <div class="philosophy-text">
        Specula is an open research platform built around three conviction-based portfolios.
        Each portfolio follows a distinct philosophy — documented and published in real time.
        <b>Concentration is intentional, not a flaw.</b> Diversification for its own sake dilutes conviction.
        We hold fewer positions, with stronger theses, and we show our work.
    </div>
</div>
""", unsafe_allow_html=True)

# ── Portfolios ────────────────────────────────────────────────────────────────
st.markdown('<div class="section-label">The Portfolios</div>', unsafe_allow_html=True)

st.markdown(
'<div class="portfolios-grid">'
'<a href="/app" target="_self" style="text-decoration:none;">'
'<div class="portfolio-card portfolio-card-active">'
'<div class="card-glow" style="background:#6366F1;"></div>'
'<div class="card-accent" style="background:linear-gradient(90deg,#6366F1,#818CF8);"></div>'
'<div class="card-number" style="color:#6366F1;">PORTFOLIO I</div>'
'<div class="card-name">Le Visionnaire</div>'
'<div class="card-subtitle">High-Conviction Equity · Growth &amp; Disruption</div>'
'<div class="card-description">Concentrated positions in companies rewriting their industries. '
'AI, digital health, space, and next-generation platforms. '
'Managed as a real paper portfolio since April 2026.</div>'
'<div class="card-badge-active badge-live">● Live</div>'
'</div></a>'
'<div class="portfolio-card portfolio-card-soon">'
'<div class="card-glow" style="background:#F97316;"></div>'
'<div class="card-accent" style="background:linear-gradient(90deg,#F97316,#FB923C);"></div>'
'<div class="card-number" style="color:#F97316;">PORTFOLIO II</div>'
'<div class="card-name">Le Nakamoto</div>'
'<div class="card-subtitle">Digital Assets · Bitcoin Treasury Plays</div>'
'<div class="card-description">Pure exposure to the Bitcoin ecosystem. Direct holdings, '
'treasury companies (DATs), and digital asset infrastructure. '
'Built on the conviction that Bitcoin is the hardest asset ever created.</div>'
'<div class="card-badge-active badge-soon">◌ In construction</div>'
'</div>'
'<div class="portfolio-card portfolio-card-soon">'
'<div class="card-glow" style="background:#F59E0B;"></div>'
'<div class="card-accent" style="background:linear-gradient(90deg,#F59E0B,#FCD34D);"></div>'
'<div class="card-number" style="color:#F59E0B;">PORTFOLIO III</div>'
'<div class="card-name">Le Bâtisseur</div>'
'<div class="card-subtitle">Quality Compounders · Capital Allocation</div>'
'<div class="card-description">The patient capital portfolio. Family-controlled businesses, '
'exceptional capital allocators, and compounders built to last decades. '
'Think Buffett — with a European lens.</div>'
'<div class="card-badge-active badge-soon">◌ In construction</div>'
'</div>'
'</div>',
unsafe_allow_html=True)

# ── Research teaser ───────────────────────────────────────────────────────────
st.markdown("""
<div class="research-teaser">
    <div class="teaser-left">
        <div class="teaser-label">Research</div>
        <div class="teaser-title">Stock Papers</div>
        <div class="teaser-sub">
            In-depth equity analysis on portfolio positions and market themes.
            Every position we hold has a written thesis — published and signed.
        </div>
    </div>
    <a href="/Research" target="_self" class="teaser-cta">Read the papers →</a>
</div>
""", unsafe_allow_html=True)

# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="specula-footer">
    <div class="footer-logo">Specula</div>
    <div class="footer-text">
        Personal paper portfolios shared for educational and informational purposes only.<br>
        Not financial advice. Not investment advice. Always conduct your own due diligence.
    </div>
</div>
""", unsafe_allow_html=True)
