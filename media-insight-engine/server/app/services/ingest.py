"""One source → ready: transcript → segments → analysis → embeddings (FR-2, FR-3; docs/dataflow.md §2)."""
import logging

import anthropic
from psycopg.types.json import Jsonb

from app.db import pool
from app.services import analyze, audio, embed, pdf, segment, web, youtube
from app.services.llm import ModelRefusal, ModelUnavailable, api_error_message
from app.services.youtube import IngestError

log = logging.getLogger("ingest")


def _status(source_id: int, status: str, error: str | None = None) -> None:
    with pool().connection() as conn:
        conn.execute("UPDATE sources SET status = %s, error = %s, progress = NULL, updated_at = now() WHERE id = %s",
                     (status, error, source_id))


def _progress(source_id: int, pct: int) -> None:
    with pool().connection() as conn:
        conn.execute("UPDATE sources SET progress = %s, updated_at = now() WHERE id = %s", (pct, source_id))


def ingest_source(source_id: int) -> None:
    with pool().connection() as conn:
        src = conn.execute(
            """SELECT s.*, c.lens_text, c.lens_tags, c.segment_seconds
               FROM sources s JOIN collections c ON c.id = s.collection_id WHERE s.id = %s""",
            (source_id,)).fetchone()
    if not src or src["archived"] or src["status"] != "queued":
        return
    _status(source_id, "transcribing")
    try:
        kind, report = src["type"], (lambda pct: _progress(source_id, pct))
        if kind == "youtube":
            meta = youtube.metadata(src["ext_id"])
            try:
                lines = youtube.captions(src["ext_id"])
            except youtube.NoCaptions:  # FR-2.2: no captions → download the audio and transcribe it
                audio_meta, lines = audio.fetch(f"https://www.youtube.com/watch?v={src['ext_id']}", report)
                meta = {**audio_meta, **{k: v for k, v in meta.items() if v is not None}, "media_url": None}
            segs = segment.by_time(lines, src["segment_seconds"], meta.get("duration_s"))
        elif kind == "audio":
            meta, lines = audio.fetch(src["media_url"] or src["url"], report)
            segs = segment.by_time(lines, src["segment_seconds"], src["duration_s"] or meta.get("duration_s"))
        elif kind == "pdf":
            meta, pages = pdf.fetch(src["url"])
            segs = segment.by_page(pages)
        else:
            meta, markdown = web.fetch(src["url"])
            segs = segment.by_heading(markdown)
        if not segs:
            raise IngestError("Nothing to index after cleaning the text")
        _save_segments(source_id, meta, segs)
        src.update({k: v for k, v in meta.items() if v is not None and not src.get(k)})

        result, model = analyze.run(src, src["lens_text"], src["lens_tags"], segs)
        info = result["segments"]
        vectors = embed.passages([f"{s.text}\n{(info.get(s.ord) or {}).get('summary') or ''}" for s in segs])
        _save_analysis(source_id, segs, result, vectors, model)
        log.info("source %s ready: %d segments, %d chapters, %d quotes",
                 source_id, len(segs), len(result["chapters"]), len(result["key_quotes"]))
    except IngestError as e:
        _status(source_id, "failed", str(e))
    except ModelRefusal as e:
        _status(source_id, "failed", f"Analysis declined by the model: {e}")
    except ModelUnavailable as e:
        _status(source_id, "failed", str(e))
    except anthropic.APIStatusError as e:  # no credits, bad key, overloaded…: show Claude's reason
        log.warning("analysis of source %s: %s", source_id, e.message)
        _status(source_id, "failed", api_error_message(e))
    except Exception as e:
        log.exception("ingest of source %s failed", source_id)
        _status(source_id, "failed", f"Unexpected error: {type(e).__name__}: {str(e)[:300]}")


def _save_segments(source_id: int, meta: dict, segs: list[segment.Seg]) -> None:
    with pool().connection() as conn, conn.transaction():
        # A retried source starts clean: never half old, half new data.
        conn.execute("DELETE FROM key_quotes WHERE source_id = %s", (source_id,))
        conn.execute("DELETE FROM chapters WHERE source_id = %s", (source_id,))
        conn.execute("DELETE FROM segments WHERE source_id = %s", (source_id,))
        with conn.cursor() as cur:
            cur.executemany(
                """INSERT INTO segments (source_id, ord, start_s, end_s, anchor, text, snippets)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                [(source_id, s.ord, s.start_s, s.end_s, s.anchor, s.text, Jsonb(s.lines) if s.lines else None)
                 for s in segs])
        # What's already known wins (e.g. an RSS feed's episode title beats the MP3 file name).
        conn.execute(
            """UPDATE sources SET title = coalesce(title, %s), host = coalesce(host, %s),
                 published_at = coalesce(published_at, %s), duration_s = coalesce(duration_s, %s),
                 media_url = coalesce(media_url, %s),
                 status = 'analyzing', progress = NULL, error = NULL, updated_at = now() WHERE id = %s""",
            (meta.get("title"), meta.get("host"), meta.get("published_at"), meta.get("duration_s"),
             meta.get("media_url"), source_id))


def _save_analysis(source_id: int, segs: list[segment.Seg], result: dict, vectors: list, model: str) -> None:
    with pool().connection() as conn, conn.transaction():
        seg_ids = {r["ord"]: r["id"] for r in conn.execute(
            "SELECT id, ord FROM segments WHERE source_id = %s", (source_id,))}
        with conn.cursor() as cur:
            cur.executemany(
                "UPDATE segments SET summary = %s, tags = %s, embedding = %s WHERE id = %s",
                [((result["segments"].get(s.ord) or {}).get("summary"),
                  (result["segments"].get(s.ord) or {}).get("tags", []), vec, seg_ids[s.ord])
                 for s, vec in zip(segs, vectors)])
            cur.executemany(
                "INSERT INTO chapters (source_id, ord, start_s, end_s, title, summary) VALUES (%s, %s, %s, %s, %s, %s)",
                [(source_id, n, c["start_s"], c["end_s"], c["title"], c["summary"])
                 for n, c in enumerate(result["chapters"])])
            cur.executemany(
                "INSERT INTO key_quotes (source_id, segment_id, ts_s, quote, is_advice) VALUES (%s, %s, %s, %s, %s)",
                [(source_id, seg_ids[q["seg"]], q["ts_s"], q["quote"], q["is_advice"]) for q in result["key_quotes"]])
        conn.execute(
            """UPDATE sources SET overview = %s, analysis_model = %s, status = 'ready', error = NULL,
                 ingested_at = now(), updated_at = now() WHERE id = %s""",
            (result["overview"], model, source_id))
