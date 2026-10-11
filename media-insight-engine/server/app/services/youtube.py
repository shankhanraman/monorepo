"""YouTube: timestamped captions (manual English first, then auto-generated) + metadata (FR-2.2, FR-2.3)."""
import html
import logging
from datetime import datetime

import yt_dlp
from youtube_transcript_api import (CouldNotRetrieveTranscript, IpBlocked, NoTranscriptFound, RequestBlocked,
                                    TranscriptsDisabled, VideoUnavailable, YouTubeTranscriptApi)

log = logging.getLogger("youtube")
LANGS = ["en", "en-US", "en-GB", "en-CA", "en-AU"]


class IngestError(Exception):
    """A readable reason the source can't be ingested; shown to the user as sources.error."""


def captions(video_id: str) -> list[dict]:
    try:
        tl = YouTubeTranscriptApi().list(video_id)
        try:
            transcript = tl.find_manually_created_transcript(LANGS)
        except NoTranscriptFound:
            transcript = tl.find_generated_transcript(LANGS)
        return [{"start": s.start, "dur": s.duration, "text": html.unescape(s.text).replace("\n", " ")}
                for s in transcript.fetch()]
    except (NoTranscriptFound, TranscriptsDisabled):
        raise IngestError("No English captions available (audio transcription is Day 2)")
    except VideoUnavailable:
        raise IngestError("Video unavailable (private, removed or region-blocked)")
    except (RequestBlocked, IpBlocked):
        raise IngestError("YouTube is blocking caption requests from this network; try again later")
    except CouldNotRetrieveTranscript as e:
        raise IngestError(f"Could not get captions: {str(e).splitlines()[0][:200]}")


def metadata(video_id: str) -> dict:
    """Title, channel, date, duration. Missing metadata is not fatal: captions are what matter."""
    try:
        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "skip_download": True}) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
    except Exception as e:
        log.warning("metadata for %s failed: %s", video_id, e)
        return {}
    upload = info.get("upload_date")
    return {"title": info.get("title"), "host": info.get("channel") or info.get("uploader"),
            "published_at": datetime.strptime(upload, "%Y%m%d").date() if upload else None,
            "duration_s": int(info["duration"]) if info.get("duration") else None}
