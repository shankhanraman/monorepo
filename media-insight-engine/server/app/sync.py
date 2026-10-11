"""make sync COLLECTION=yale → python -m app.sync yale

Asks the running server to sync (so all work stays in one process), prints the sync log, then
follows the sources until none is in progress and prints how long each one took (AC-1, AC-9).
"""
import json
import sys
import time
import urllib.error
import urllib.request

from app.config import settings

ICON = {"queued": "⏳", "skipped": "✓", "failed": "✗", "archived": "🗄"}
BUSY = {"queued", "transcribing", "analyzing"}


def call(method: str, path: str):
    req = urllib.request.Request(settings.api_url + path, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        detail = json.loads(e.read() or b"{}").get("detail", e.reason)
        sys.exit(f"error {e.code}: {detail}")
    except urllib.error.URLError as e:
        sys.exit(f"server not reachable at {settings.api_url} ({e.reason}). Is `docker compose up` running?")


def main(slug: str, wait: bool = True) -> int:
    log = call("POST", f"/sync?collection={slug}")
    print(f"Sync {slug}: " + ", ".join(f"{v} {k}" for k, v in log["summary"].items()))
    for e in log["entries"]:
        print(f"  {ICON[e['action']]} {e['action']:<8} {e['label'] or e['url']}\n             {e['reason']}")
    queued = {e["source_id"] for e in log["entries"] if e["action"] == "queued"}
    if not wait or not queued:
        return 1 if log["summary"]["failed"] else 0
    print("\nIngesting (Ctrl+C stops watching; the server keeps working)…")
    t0, last, done_at = time.monotonic(), {}, {}
    while True:
        sources = {s["id"]: s for s in call("GET", f"/collections/{slug}/sources") if s["id"] in queued}
        for sid, s in sources.items():
            if last.get(sid) != s["status"]:
                last[sid] = s["status"]
                elapsed = time.monotonic() - t0
                print(f"  [{elapsed:5.0f}s] {s['title'] or s['label'] or s['url']}: {s['status']}"
                      + (f" ({s['error']})" if s["error"] else ""))
                if s["status"] not in BUSY:
                    done_at[sid] = elapsed
        if all(s["status"] not in BUSY for s in sources.values()):
            break
        time.sleep(3)
    failed = [s for s in sources.values() if s["status"] == "failed"]
    print(f"\nDone in {time.monotonic() - t0:.0f}s: {len(sources) - len(failed)} ready, {len(failed)} failed.")
    return 1 if failed or log["summary"]["failed"] else 0


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        sys.exit("usage: python -m app.sync <collection> [--no-wait]")
    sys.exit(main(args[0], wait="--no-wait" not in sys.argv))
