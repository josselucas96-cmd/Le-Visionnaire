"""Render report HTML file(s) to PDF with headless Chromium (Playwright).

    python scripts/render_pdf.py reports/drafts            # every .html under the folder
    python scripts/render_pdf.py path/to/report.html [...]

Replaces the manual Chrome Ctrl+P step (A4 portrait, no margins, backgrounds on).
"""
import sys
from pathlib import Path


def html_to_pdf(html_path: Path, pdf_path: Path | None = None) -> Path:
    from playwright.sync_api import sync_playwright
    pdf_path = pdf_path or html_path.with_suffix(".pdf")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(html_path.resolve().as_uri(), wait_until="networkidle")
        page.emulate_media(media="print")
        page.pdf(path=str(pdf_path), format="A4", print_background=True,
                 margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
                 prefer_css_page_size=True)
        browser.close()
    return pdf_path


def main() -> int:
    targets = []
    for arg in sys.argv[1:] or ["reports/drafts"]:
        p = Path(arg)
        targets += sorted(p.rglob("*.html")) if p.is_dir() else [p]
    if not targets:
        print("no HTML files found"); return 1
    for t in targets:
        out = html_to_pdf(t)
        print(f"{t} -> {out} ({out.stat().st_size/1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
