"""Web pages via Crawl4AI (headless Chromium, so JavaScript pages work): clean Markdown + metadata (FR-2.2)."""
import asyncio
import threading
from datetime import date
from urllib.parse import urlsplit

from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig
from crawl4ai.content_filter_strategy import PruningContentFilterLXML
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator

from app.services.youtube import IngestError

MIN_WORDS = 150
DATE_KEYS = ("article:published_time", "og:published_time", "datePublished", "date", "article:modified_time")


async def _crawl(url: str):
    run = CrawlerRunConfig(cache_mode=CacheMode.BYPASS, page_timeout=60000, verbose=False,
                           markdown_generator=DefaultMarkdownGenerator(content_filter=PruningContentFilterLXML()))
    # ponytail: one browser per page; share a crawler if many web sources appear
    async with AsyncWebCrawler(config=BrowserConfig(headless=True, verbose=False)) as crawler:
        return await crawler.arun(url, config=run)


def _date(meta: dict) -> date | None:
    for key in DATE_KEYS:
        value = str(meta.get(key) or "")[:10]
        try:
            return date.fromisoformat(value)
        except ValueError:
            continue
    return None


_one_at_a_time = threading.Lock()


def fetch(url: str) -> tuple[dict, str]:
    """(metadata, markdown). Runs in a worker thread, so it gets its own event loop."""
    # ponytail: Crawl4AI keeps a SQLite cache even in BYPASS mode; parallel crawls hit "database is locked".
    # Pages take seconds, so crawl one at a time.
    with _one_at_a_time:
        result = asyncio.run(_crawl(url))
    if not result.success:
        raise IngestError(f"Could not load page: {(result.error_message or 'unknown error')[:200]}")
    md = result.markdown.fit_markdown or result.markdown.raw_markdown
    if len(md.split()) < MIN_WORDS:
        md = result.markdown.raw_markdown  # the filter can be too aggressive on short pages
    if len(md.split()) < MIN_WORDS:
        raise IngestError("Page had no readable text")
    meta = result.metadata or {}
    return {"title": meta.get("title") or meta.get("og:title"),
            "host": meta.get("og:site_name") or urlsplit(url).hostname,
            "published_at": _date(meta), "duration_s": None}, md
