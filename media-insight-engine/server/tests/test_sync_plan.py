from app.config import load_collection
from app.services.sync import plan_sync
from tests.conftest import write

YT = "https://www.youtube.com/watch?v="


def collection(config_dir, sources: str):
    write(config_dir / "collections" / "yale.yaml", "name: Yale\nlens: test-lens\nsources:\n" + sources)
    return load_collection("yale", config_dir)


def by_url(steps):
    return {s.url: (s.action, s.op, s.reason) for s in steps}


def test_new_skip_retry_archive_restore(config_dir):
    col = collection(config_dir, f"""\
  - url: https://youtu.be/aaaaaaaaaaa
  - url: {YT}bbbbbbbbbbb
  - url: {YT}ccccccccccc
  - url: {YT}ddddddddddd
  - url: {YT}eeeeeeeeeee
""")
    existing = {
        f"{YT}bbbbbbbbbbb": {"id": 2, "status": "ready", "archived": False, "error": None},
        f"{YT}ccccccccccc": {"id": 3, "status": "transcribing", "archived": False, "error": None},
        f"{YT}ddddddddddd": {"id": 4, "status": "failed", "archived": False, "error": "boom"},
        f"{YT}eeeeeeeeeee": {"id": 5, "status": "ready", "archived": True, "error": None},
        f"{YT}zzzzzzzzzzz": {"id": 9, "status": "ready", "archived": False, "error": None},
        f"{YT}yyyyyyyyyyy": {"id": 8, "status": "ready", "archived": True, "error": None},   # already archived
    }
    steps = by_url(plan_sync(col, existing))
    assert steps[f"{YT}aaaaaaaaaaa"] == ("queued", "insert", "New URL")
    assert steps[f"{YT}bbbbbbbbbbb"] == ("skipped", "refresh", "Already ready")
    assert steps[f"{YT}ccccccccccc"] == ("skipped", "refresh", "Already being ingested (transcribing)")
    assert steps[f"{YT}ddddddddddd"] == ("queued", "requeue", "Retrying (last error: boom)")
    assert steps[f"{YT}eeeeeeeeeee"] == ("skipped", "refresh", "Restored, Already ready")
    assert steps[f"{YT}zzzzzzzzzzz"] == ("archived", "archive", "Removed from yale.yaml")
    assert f"{YT}yyyyyyyyyyy" not in steps                       # nothing to say twice


def test_second_run_is_all_skipped(config_dir):
    col = collection(config_dir, f"  - url: {YT}aaaaaaaaaaa\n  - url: https://x.edu/page\n")
    existing = {f"{YT}aaaaaaaaaaa": {"id": 1, "status": "ready", "archived": False, "error": None},
                "https://x.edu/page": {"id": 2, "status": "ready", "archived": False, "error": None}}
    assert {s.action for s in plan_sync(col, existing)} == {"skipped"}


def test_invalid_duplicate_day2_and_bad_youtube_are_logged(config_dir):
    col = collection(config_dir, """\
  - url: https://x.edu/page/
  - url: https://x.edu/page?utm_source=mail
  - url: https://x.edu/episode.mp3
  - url: https://x.edu/guide.pdf
  - url: https://x.edu/video
    type: youtube
  - url: ftp://x.edu/file
  - label: missing url
""")
    steps = plan_sync(col, {})
    actions = [(s.action, s.reason.split(" (")[0]) for s in steps]
    assert actions[0] == ("queued", "New URL")
    assert actions[1] == ("failed", "Duplicate of entry 1 in the file")
    assert actions[2] == ("failed", "Type 'audio' is not supported until Day 2")
    assert actions[3] == ("failed", "Type 'pdf' is not supported until Day 2")
    assert actions[4] == ("failed", "Not a YouTube video URL")
    assert actions[5][0] == "failed" and actions[5][1].startswith("Invalid URL")
    assert actions[6][0] == "failed" and steps[6].url == "(no url)"
    assert all(s.op == "none" for s in steps[1:])
