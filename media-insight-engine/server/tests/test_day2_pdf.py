"""PDF ingest on a real PDF, printed by the image's Chromium (skipped where Playwright isn't installed)."""
import pytest

from app.services import pdf
from app.services.segment import by_page
from app.services.youtube import IngestError

playwright = pytest.importorskip("playwright.sync_api")

HTML = """<html><head><title>Common Data Set 2025-2026</title></head><body>
<h1>Common Data Set 2025-2026</h1><p>{p1}</p>
<div style="break-before: page"></div><h2>C9 First-time first-year profile</h2><p>{p2}</p></body></html>"""


def make_pdf(html: str) -> bytes:
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_content(html)
        data = page.pdf(format="A4")
        browser.close()
    return data


def test_pdf_pages_become_segments():
    data = make_pdf(HTML.format(p1="General information about admission. " * 20,
                                p2="Percent submitting SAT scores 54 percent. " * 10))
    meta, pages = pdf.read(data, "https://oir.example.edu/cds-2025-2026.pdf")
    assert len(pages) == 2 and "Percent submitting SAT scores" in pages[1]
    assert meta["host"] == "oir.example.edu" and meta["title"]          # from metadata or the file name
    segs = by_page(pages)
    assert [s.anchor for s in segs] == ["Page 1", "Page 2"]


def test_pdf_without_text_is_rejected():
    blank = make_pdf("<html><body><div style='width:10px;height:10px;background:#000'></div></body></html>")
    with pytest.raises(IngestError, match="no text layer"):
        pdf.read(blank, "https://x.edu/scan.pdf")
