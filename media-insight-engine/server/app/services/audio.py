"""Podcast audio (and YouTube videos without captions): download → faster-whisper → timestamped lines (FR-2.2).

The audio file only lives in a temporary folder while it is transcribed (PRD: no audio is stored).
"""
import logging
import os
import tempfile
import threading
from datetime import datetime, timezone
from typing import Callable

import yt_dlp

from app.services.youtube import IngestError

log = logging.getLogger("audio")
MAX_BYTES = 500 * 1024 * 1024
_model = None
_model_lock = threading.Lock()
_one_at_a_time = threading.Lock()  # transcription already uses every core


def _whisper():
    global _model
    with _model_lock:
        if _model is None:
            from faster_whisper import WhisperModel
            name = os.environ.get("WHISPER_MODEL", "large-v3-turbo")
            log.info("loading whisper model %s", name)
            _model = WhisperModel(name, device="cpu", compute_type="int8", cpu_threads=os.cpu_count() or 4,
                                  download_root=os.environ.get("WHISPER_DIR"))
    return _model


def _info_meta(info: dict, url: str) -> dict:
    ts = info.get("timestamp") or info.get("release_timestamp")
    upload = info.get("upload_date") or info.get("release_date")
    published = (datetime.fromtimestamp(ts, timezone.utc).date() if ts
                 else datetime.strptime(upload, "%Y%m%d").date() if upload else None)
    media = info.get("url") if info.get("vcodec") in (None, "none") else None  # direct audio, not a video stream
    return {"title": info.get("title"), "host": info.get("channel") or info.get("uploader") or info.get("series"),
            "published_at": published, "duration_s": int(info["duration"]) if info.get("duration") else None,
            "media_url": media or (url if info.get("extractor") == "generic" else None)}


def download(url: str, folder: str) -> tuple[str, dict]:
    """(file path, metadata). Works for direct MP3s and any page yt-dlp supports."""
    opts = {"format": "bestaudio/best", "outtmpl": os.path.join(folder, "audio.%(ext)s"), "noplaylist": True,
            "quiet": True, "no_warnings": True, "max_filesize": MAX_BYTES}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            path = info["requested_downloads"][0]["filepath"] if info.get("requested_downloads") else ydl.prepare_filename(info)
    except yt_dlp.utils.DownloadError as e:
        raise IngestError(f"Could not download the audio: {str(e).removeprefix('ERROR: ')[:200]}") from e
    if not os.path.exists(path):
        raise IngestError("Could not download the audio (file too large or no audio stream)")
    return path, _info_meta(info, url)


def progress_reporter(duration_s: float, report: Callable[[int], None], every: int = 5) -> Callable[[float], None]:
    """update(seconds_done) → calls report(pct) each time progress moves another `every` %, never 100 before the end."""
    last = -every

    def update(done_s: float) -> None:
        nonlocal last
        pct = min(99, int(done_s / duration_s * 100)) if duration_s else 0
        if pct >= last + every:
            report(pct)
            last = pct
    return update


def transcribe(path: str, on_progress: Callable[[int], None]) -> list[dict]:
    """Caption-like lines [{start, dur, text}] for segment.by_time()."""
    with _one_at_a_time:
        segments, info = _whisper().transcribe(path, language="en", vad_filter=True)
        update = progress_reporter(info.duration, on_progress)
        lines = []
        for seg in segments:  # a generator: transcription happens while we iterate
            text = seg.text.strip()
            if text:
                lines.append({"start": seg.start, "dur": seg.end - seg.start, "text": text})
            update(seg.end)
    if not lines:
        raise IngestError("No speech found in the audio")
    return lines


def fetch(url: str, on_progress: Callable[[int], None]) -> tuple[dict, list[dict]]:
    with tempfile.TemporaryDirectory(prefix="mie-audio-") as folder:
        path, meta = download(url, folder)
        on_progress(0)
        return meta, transcribe(path, on_progress)
