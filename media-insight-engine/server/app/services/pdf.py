"""PDF documents: text per page with pypdf (FR-2.2). Scanned PDFs (no text layer) are rejected."""
import io
import re
import urllib.request
from datetime import datetime
from pathlib import PurePosixPath
from urllib.parse import unquote, urlsplit

from pypdf import PdfReader

from app.services.youtube import IngestError

MAX_BYTES = 50 * 1024 * 1024
MIN_WORDS = 30
UA = "Mozilla/5.0 (media-insight-engine)"


def download(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read(MAX_BYTES + 1)
    except Exception as e:
        raise IngestError(f"Could not download the PDF ({str(e)[:150]})") from e
    if len(data) > MAX_BYTES:
        raise IngestError("PDF is larger than 50 MB")
    if not data.startswith(b"%PDF"):
        raise IngestError("The URL did not return a PDF")
    return data


def _clean(text: str) -> str:
    lines = (" ".join(line.split()) for line in text.splitlines())
    return "\n".join(line for line in lines if line)


def read(data: bytes, url: str) -> tuple[dict, list[str]]:
    """(metadata, text of each page)."""
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted and not reader.decrypt(""):
            raise IngestError("PDF is password-protected")
        pages = [_clean(page.extract_text() or "") for page in reader.pages]
        info = reader.metadata
    except IngestError:
        raise
    except Exception as e:
        raise IngestError(f"Could not read the PDF ({type(e).__name__})") from e
    if sum(len(p.split()) for p in pages) < MIN_WORDS:
        raise IngestError("PDF has no text layer (scanned document); OCR is not supported")
    created = getattr(info, "creation_date", None) if info else None
    title = (getattr(info, "title", None) or "").strip() if info else ""
    if not title or re.fullmatch(r"(untitled|microsoft word.*|document\d*)", title, re.I):
        title = unquote(PurePosixPath(urlsplit(url).path).stem).replace("-", " ").replace("_", " ") or None
    return {"title": title, "host": urlsplit(url).hostname,
            "published_at": created.date() if isinstance(created, datetime) else None, "duration_s": None}, pages


def fetch(url: str) -> tuple[dict, list[str]]:
    return read(download(url), url)
