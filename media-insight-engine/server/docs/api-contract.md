# API contract: Media Insight Engine (Day 1 + Day 2)

The machine-readable contract is [openapi.yaml](openapi.yaml), OpenAPI 3.1, contract version **0.2.0**. This page explains the same contract for the frontend: what to call from each screen, what comes back, and the few rules the UI must follow.

## What changed in Day 2 (0.1.0 → 0.2.0)

All changes only add things, so Day-1 screens keep working. To use the new features:

| Change | Where | UI work |
|---|---|---|
| New source types `audio` (podcast episodes) and `pdf` | `type` on sources and `source_type` on citations | type badges; source page: `<audio>` player for audio, page sections for PDFs |
| `progress` (0–100) while transcribing | `SourceSummary` | show "transcribing 42 %" (on CPU an episode takes ~2× its length) |
| `stale` flag on sources | `SourceSummary` | "may be outdated" badge in the list and on the source page |
| `feed_url` (episode came from an RSS feed) | `SourceSummary`, `SyncEntry` | "from feed" note; group the sync log |
| `media_url` (playable audio) | `SourceDetail` | `src` of the `<audio>` element |
| Sync `action: "feed"` | sync log | a line saying how many episodes a feed entry selected |
| `GET /bank-runs/{id}/report.pdf` | question-bank report | "Export PDF" next to "Export Markdown" |
| Audio and PDF link formats | `deep_link`, `app_link`, `label` | none: render them like the existing ones (§3, Source page) |

If this page and `openapi.yaml` ever disagree, **`openapi.yaml` wins**. Changes to either go through a PR that updates both.

---

## 1. Basics

| | |
|---|---|
| Base URL | `http://localhost:8003` (docker compose). The Vite dev server on `http://localhost:5176` is allowed by CORS |
| Auth | none on Day 1 (single user, local) |
| Format | JSON in and out, UTF-8. One exception: the Markdown report download |
| Collection ids | slugs from the config file name: `yale`, `mit`. `all` is accepted **only** by the ask endpoint |
| Other ids | integers |
| Times | seconds: `start_s`, `end_s`, `ts_s` for `youtube` and `audio`. **`web` and `pdf`:** these hold the *section order number*, not seconds. Use `label`/`anchor` for display |
| Dates | `published_at` is `YYYY-MM-DD` or `null` (unknown). Other timestamps are ISO date-times in UTC |
| Errors | `{"detail": "message"}`. Request validation errors (422) use FastAPI's list form `{"detail": [{"loc": [...], "msg": "...", "type": "..."}]}` |

### Working before the backend exists

```bash
# Mock server that answers with the examples from openapi.yaml, on the real port:
npx @stoplight/prism-cli mock server/docs/openapi.yaml -p 8003

# TypeScript types generated from the contract:
npx openapi-typescript server/docs/openapi.yaml -o client/src/api/schema.d.ts
```

The JSON samples below are the same examples, so you can also paste them into fixtures.

---

## 2. Which screen calls what

| Screen | Calls |
|---|---|
| Header: college picker | `GET /collections` |
| Sources list + Sync button + sync log | `GET /collections/{id}/sources` (poll), `POST /sync?collection={id}`, `GET /collections/{id}/sync-log` |
| Source page (YouTube or audio player, overview, chapters, timeline, quotes; sections for web/PDF) | `GET /sources/{id}` |
| Ask chat | `POST /collections/{id or all}/ask`, `POST /notes` |
| Notes | `GET /notes`, `DELETE /notes/{id}` |
| Question Bank + report | `GET`/`POST /collections/{id}/question-banks`, `DELETE /question-banks/{id}`, `POST /question-banks/{id}/run`, `GET /bank-runs/{id}` (poll), `GET /bank-runs/{id}/report.md`, `GET /bank-runs/{id}/report.pdf` |

---

## 3. Endpoints

### Health
```bash
curl http://localhost:8003/health
```
```json
{ "status": "ok" }
```

### List collections
`GET /collections` returns every collection that has a config file, including ones that were never synced.
```bash
curl http://localhost:8003/collections
```
```json
[
  {
    "id": "yale",
    "name": "Yale",
    "lens_name": "undergrad-admissions",
    "lens_tags": ["testing", "essays", "why-major", "ea-ed", "extracurriculars", "recommendations", "interviews", "financial-aid"],
    "focus_note": "Early Action, class of 2031",
    "segment_seconds": 60,
    "source_counts": { "total": 5, "ready": 3, "in_progress": 1, "failed": 1, "archived": 0 },
    "last_synced_at": "2026-10-11T14:05:40Z"
  }
]
```
Use `lens_tags` to fill the tag filter in Ask.

### Sync a collection
`POST /sync?collection=yale` validates `yale.yaml` and returns the sync log right away. Ingest continues in the background.
```bash
curl -X POST "http://localhost:8003/sync?collection=yale"
```
```json
{
  "id": 21,
  "collection_id": "yale",
  "created_at": "2026-10-11T14:05:40Z",
  "summary": { "queued": 2, "skipped": 3, "failed": 1, "archived": 1 },
  "entries": [
    { "url": "https://www.youtube.com/watch?v=abc123XYZ00", "label": "Admissions podcast – supplemental essays", "action": "skipped", "reason": "Already ready", "source_id": 12, "feed_url": null },
    { "url": "https://admissions.yale.edu/essays", "label": "Essay prompts page", "action": "queued", "reason": "New URL", "source_id": 13, "feed_url": null },
    { "url": "https://www.youtube.com/watch?v=def456UVW11", "label": "Testing policy Q&A", "action": "skipped", "reason": "Already being ingested (transcribing)", "source_id": 15, "feed_url": null },
    { "url": "https://open.spotify.com/episode/4abc", "label": "Spotify episode", "action": "failed", "reason": "Spotify audio is DRM-protected: use the show's RSS feed instead", "source_id": null, "feed_url": null },
    { "url": "https://feeds.megaphone.fm/insideyaleadmissions", "label": "Inside the Yale Admissions Office", "action": "feed", "reason": "Feed read: 3 of 57 episodes selected (latest 3)", "source_id": null, "feed_url": null },
    { "url": "https://traffic.megaphone.fm/YALE1234567890.mp3", "label": "Episode 42: Testing policy", "action": "queued", "reason": "New episode", "source_id": 21, "feed_url": "https://feeds.megaphone.fm/insideyaleadmissions" },
    { "url": "https://traffic.megaphone.fm/YALE1234567889.mp3", "label": "Episode 41: Supplemental essays", "action": "skipped", "reason": "Already ready", "source_id": 20, "feed_url": "https://feeds.megaphone.fm/insideyaleadmissions" },
    { "url": "https://www.youtube.com/watch?v=old000000AA", "label": "Old webinar", "action": "archived", "reason": "Removed from yale.yaml", "source_id": 9, "feed_url": null }
  ]
}
```
| `action` | Show as |
|---|---|
| `queued` | ⏳ new or retried; ingest started |
| `skipped` | ✓ already there (`reason` says why) |
| `failed` | ✗ red, with `reason`. Nothing was ingested |
| `archived` | 🗄 removed from the file; hidden from answers |
| `feed` | 📻 an RSS feed was read; `reason` says how many episodes were selected. Its episodes follow as normal lines with `feed_url` set; indent them under the feed line. Not counted in `summary` |

| Status | Meaning |
|---|---|
| 404 | no such config file |
| 409 | a sync for this collection is already running: disable the button and retry later |
| 422 | the YAML file itself is broken; show `detail` |

`GET /collections/{id}/sync-log` returns the latest log in the same shape (404 if never synced). Show it under the Sync button when the page loads.

### List sources
`GET /collections/{id}/sources` (add `?include_archived=true` to also see archived ones).
```bash
curl http://localhost:8003/collections/yale/sources
```
```json
[
  {
    "id": 12, "collection_id": "yale", "type": "youtube",
    "url": "https://www.youtube.com/watch?v=abc123XYZ00",
    "label": "Admissions podcast – supplemental essays", "priority": "high",
    "title": "Inside the Yale Admissions Office: Supplemental Essays", "host": "Yale Admissions",
    "published_at": "2025-09-15", "duration_s": 2112,
    "status": "ready", "error": null, "archived": false,
    "ingested_at": "2026-10-11T14:07:02Z", "segment_count": 36,
    "progress": null, "stale": false, "feed_url": null
  },
  {
    "id": 21, "collection_id": "yale", "type": "audio",
    "url": "https://traffic.megaphone.fm/YALE1234567890.mp3",
    "label": "Episode 42: Testing policy", "priority": "normal",
    "title": "Episode 42: Testing policy", "host": "Inside the Yale Admissions Office",
    "published_at": "2026-09-01", "duration_s": 2160,
    "status": "transcribing", "error": null, "archived": false,
    "ingested_at": null, "segment_count": 0,
    "progress": 42, "stale": false, "feed_url": "https://feeds.megaphone.fm/insideyaleadmissions"
  },
  {
    "id": 14, "collection_id": "yale", "type": "youtube",
    "url": "https://www.youtube.com/watch?v=noCaps00000",
    "label": "Info session recording", "priority": "normal",
    "title": "Yale Virtual Information Session", "host": "Yale Admissions",
    "published_at": "2024-11-02", "duration_s": 3605,
    "status": "failed", "error": "Video unavailable (private, removed or region-blocked)",
    "archived": false, "ingested_at": null, "segment_count": 0,
    "progress": null, "stale": true, "feed_url": null
  }
]
```
- Status order: `queued → transcribing → analyzing → ready` or `failed` (with `error`).
- `title` is `null` until metadata is fetched. Fall back to `label`, then `url`.
- **`progress`** (Day 2) is set while an audio source, or a YouTube video without captions, is `transcribing`: show "transcribing 42 %" or a small progress bar. Transcription is slow on CPU (about 2× the episode's length: a 37-minute episode took 1 h 15 min), so keep polling and show the percentage.
- **`stale`** (Day 2): show a "may be outdated" badge. It's true when the source is older than 18 months (the lens setting) or has no date.
- **`feed_url`** (Day 2): the episode came from an RSS feed; you can show "from feed".

### Source page
`GET /sources/{id}`
```bash
curl http://localhost:8003/sources/12
```
```json
{
  "id": 12, "collection_id": "yale", "type": "youtube",
  "url": "https://www.youtube.com/watch?v=abc123XYZ00", "ext_id": "abc123XYZ00",
  "label": "Admissions podcast – supplemental essays", "priority": "high",
  "title": "Inside the Yale Admissions Office: Supplemental Essays", "host": "Yale Admissions",
  "published_at": "2025-09-15", "duration_s": 2112,
  "status": "ready", "error": null, "archived": false,
  "ingested_at": "2026-10-11T14:07:02Z", "segment_count": 36,
  "progress": null, "stale": false, "feed_url": null, "media_url": null,
  "overview": "Two Yale admissions officers explain how the supplemental essays are read. ...",
  "chapters": [
    { "id": 102, "start_s": 570, "end_s": 1065, "title": "Supplemental essays", "summary": "Each short answer should add something new. ..." }
  ],
  "segments": [
    {
      "id": 5001, "ord": 12, "start_s": 720, "end_s": 780, "anchor": null,
      "text": "so when you write about why you want to study a major, we really want to hear what got you curious in the first place...",
      "summary": "Officers want the origin of the interest in the major, told through a specific experience.",
      "tags": ["essays", "why-major"],
      "deep_link": "https://youtu.be/abc123XYZ00?t=720"
    }
  ],
  "key_quotes": [
    { "id": 301, "segment_id": 5001, "ts_s": 731, "quote": "we really want to hear what got you curious in the first place", "is_advice": true, "deep_link": "https://youtu.be/abc123XYZ00?t=731" }
  ]
}
```
UI rules for this page:
- **YouTube:** embed the player with `ext_id`. Clicking any timestamp (chapter, segment, quote) seeks the player to that second (PRD AC-3: within ±5 s).
- **On load, read `?t=<seconds>`** and seek there. Citations link here as `/sources/12?t=720`.
- **Audio sources** (Day 2): render a native `<audio controls src={media_url}>`. Timestamp clicks and `?t=` set `audio.currentTime = seconds` and call `play()`. Everything else (chapters, minute timeline, quotes) is the same as YouTube. The mock answers `GET /sources/21` with the audio example (Prism: header `Prefer: example=audio`).
- **Web sources:** no player. Render each segment as a section with `id="seg-<segment id>"` and `anchor` as the heading. Citations link here as `/sources/13#seg-6010`; scroll to that element.
- **PDF sources** (Day 2): same as web; `anchor` is "Page 3". Each section's "Open" link is its `deep_link` (`…pdf#page=3`, which browsers' PDF viewers open at that page).
- Show the raw `text` next to each `summary` (collapsible), so users can catch caption and speech-to-text errors.
- Show the `stale` badge next to the date.
- Label key quotes **"verbatim"**.
- `chapters`, `segments` and `key_quotes` are empty arrays until `status` is `ready`.

### Ask (grounded Q&A)
`POST /collections/{id}/ask`. Use `all` as the id to search every college.
```bash
curl -X POST http://localhost:8003/collections/yale/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What does Yale look for in the why-this-major short answer?"}'
```
Full request (everything except `question` is optional):
```json
{
  "question": "And how long should it be?",
  "history": [
    { "question": "What does Yale look for in the why-this-major short answer?", "answer_md": "Officers want ... [1] ..." }
  ],
  "filters": { "source_ids": [12], "tags": ["essays"], "date_from": "2024-01-01", "date_to": null }
}
```
- `history`: earlier turns of the chat, oldest first, maximum 10. The server keeps no chat state, so the client sends it.
- `question`: 3–2000 characters.

Response (covered):
```json
{
  "question": "What does Yale look for in the why-this-major short answer?",
  "label": "Summary of sources",
  "answer_md": "Officers want to know where your interest in the major came from, told through one specific experience rather than a list of achievements [1]. They also look for how you would use Yale's resources in that field, such as particular courses or research [2].",
  "coverage": "strong",
  "not_covered": false,
  "citations": [
    {
      "n": 1, "segment_id": 5001, "source_id": 12, "collection_id": "yale", "source_type": "youtube",
      "source_title": "Inside the Yale Admissions Office: Supplemental Essays", "host": "Yale Admissions",
      "published_at": "2025-09-15", "start_s": 720, "end_s": 780, "anchor": null, "label": "12:00–13:00",
      "snippet": "so when you write about why you want to study a major, we really want to hear what got you curious in the first place...",
      "deep_link": "https://youtu.be/abc123XYZ00?t=720", "app_link": "/sources/12?t=720", "stale": false
    },
    {
      "n": 2, "segment_id": 6010, "source_id": 13, "collection_id": "yale", "source_type": "web",
      "source_title": "Essays | Yale College Undergraduate Admissions", "host": "admissions.yale.edu",
      "published_at": null, "start_s": 3, "end_s": 3, "anchor": "Short Answer Questions", "label": "Short Answer Questions",
      "snippet": "Tell us about a topic or idea that excites you and is related to one or more academic areas you selected above...",
      "deep_link": "https://admissions.yale.edu/essays#:~:text=Tell%20us%20about%20a%20topic",
      "app_link": "/sources/13#seg-6010", "stale": true
    }
  ],
  "closest": [],
  "stale_warning": "One cited source has no publish date. Admissions policies change every year: verify on the official Yale admissions site.",
  "conflicts": null,
  "retried": false
}
```
Response (not covered):
```json
{
  "question": "What is Yale's hockey recruiting process?",
  "label": "Summary of sources",
  "answer_md": "Not covered in your sources.",
  "coverage": "none",
  "not_covered": true,
  "citations": [],
  "closest": [
    { "n": 1, "segment_id": 5120, "source_id": 12, "collection_id": "yale", "source_type": "youtube",
      "source_title": "Inside the Yale Admissions Office: Supplemental Essays", "host": "Yale Admissions",
      "published_at": "2025-09-15", "start_s": 1500, "end_s": 1560, "anchor": null, "label": "25:00–26:00",
      "snippet": "a lot of students ask about athletics and the role of coaches...",
      "deep_link": "https://youtu.be/abc123XYZ00?t=1500", "app_link": "/sources/12?t=1500", "stale": false }
  ],
  "stale_warning": null,
  "conflicts": null,
  "retried": true
}
```
How to render an answer:
1. Show `label` ("Summary of sources") above the answer.
2. `answer_md` is plain text with paragraphs (`\n\n`) and `[n]` markers, and nothing else. Turn each `[n]` into a link to the citation card with the same `n`. Every `[n]` is guaranteed to have a matching citation.
3. A citation card shows:
   - `source_title`, `published_at` (or "date unknown"), `label`, and a ⚠ if `stale`;
   - the `snippet`;
   - two links: **"Open"** → `deep_link` (new tab) and **"Play here"** → `app_link` (in-app route).
   - When the question was asked across `all`, also show `collection_id`.
4. Banners: `stale_warning` (amber) and `conflicts` (amber) when not null.
5. `not_covered: true` → show "Not covered in your sources" plainly, then `closest` as "Closest moments" cards. Never show the closest cards as an answer.
6. A coverage badge: strong / partial / none.
7. "Save to notes" posts the answer to `POST /notes` (below).

Latency is usually 3–10 s, so show a spinner. On 502, show "Answer failed, try again".

### Notes
```bash
curl -X POST http://localhost:8003/notes -H "Content-Type: application/json" -d '{
  "collection_id": "yale",
  "question": "What does Yale look for in the why-this-major short answer?",
  "answer_md": "Officers want the origin of your interest, told through one specific experience [1].",
  "coverage": "strong",
  "citations": [],
  "comment": "Use for Aksh'"'"'s draft"
}'
```
- Send the `citations` array from the ask response unchanged (it's `[]` above only to keep the example short).
- Responses:
  - `POST /notes` returns `201` with the note plus `id` and `created_at`;
  - `GET /notes?collection=yale` returns the notes, newest first;
  - `DELETE /notes/{id}` returns `204`.

### Question banks
Save a bank. The **client** turns pasted text or an uploaded file into a clean list first:
- **Text:** one question per line.
- **CSV:** the first column; drop the first row if it is a header (its text is `question`, in any case).
- Trim each line, drop empty lines and exact duplicates. Allow 1–100 questions of 3–2000 characters each.

```bash
curl -X POST http://localhost:8003/collections/yale/question-banks -H "Content-Type: application/json" -d '{
  "name": "Yale supplements + testing",
  "questions": [
    "What does Yale look for in the why-this-major short answer?",
    "Is the SAT/ACT required and how much does it matter?"
  ]
}'
```
```json
{ "id": 3, "collection_id": "yale", "name": "Yale supplements + testing",
  "questions": ["What does Yale look for in the why-this-major short answer?", "Is the SAT/ACT required and how much does it matter?"],
  "created_at": "2026-10-11T14:58:00Z", "latest_run_id": null }
```
- `GET /collections/yale/question-banks` lists banks, newest first.
- `DELETE /question-banks/{id}` removes a bank and its runs (`204`).
- `latest_run_id` lets the screen reopen the last report.

Run a bank:
```bash
curl -X POST http://localhost:8003/question-banks/3/run
```
- Returns `202` with a `BankRun` with `status: "running"`, `done: 0` and every item `pending`.
- `409` means a run of this bank is already in progress.
- An optional body `{"filters": {...}}` applies the same filters as Ask to every question.

Poll the run every 2 s with `GET /bank-runs/{id}` until `status` is `done` or `failed`:
```json
{
  "id": 7, "bank_id": 3, "bank_name": "Yale supplements + testing", "collection_id": "yale",
  "status": "done", "done": 2, "total": 2,
  "created_at": "2026-10-11T15:00:00Z", "finished_at": "2026-10-11T15:00:24Z",
  "items": [
    {
      "index": 0,
      "question": "What does Yale look for in the why-this-major short answer?",
      "status": "done",
      "answer_md": "Officers want the origin of your interest, told through one specific experience [1].",
      "coverage": "strong",
      "watch": [
        { "n": 1, "segment_id": 5001, "source_id": 12, "collection_id": "yale", "source_type": "youtube",
          "source_title": "Inside the Yale Admissions Office: Supplemental Essays", "host": "Yale Admissions",
          "published_at": "2025-09-15", "start_s": 720, "end_s": 780, "anchor": null, "label": "12:00–13:00",
          "snippet": "...we really want to hear what got you curious in the first place...",
          "deep_link": "https://youtu.be/abc123XYZ00?t=720", "app_link": "/sources/12?t=720", "stale": false }
      ],
      "stale_warning": null,
      "error": null
    }
  ]
}
```
- Progress bar: `done / total`. Items fill in as they finish; render each one as soon as its `status` is `done`.
- Report row per item:
  - the short answer, rendered like Ask with `[n]` matching `watch[].n`;
  - a coverage badge;
  - **"Watch these"**: the `watch` list (already ranked, 2–5 entries, fewer only if fewer were cited), linked with `deep_link`;
  - `stale_warning` if set.
- An item with `status: "failed"` shows its `error` and doesn't stop the run.

Export:
- **Markdown:** `GET /bank-runs/{id}/report.md` returns a file download (`text/markdown`, `Content-Disposition: attachment`). Link to it directly. It returns `409` while the run is still running.
- **PDF** (Day 2): `GET /bank-runs/{id}/report.pdf` returns a file download (`application/pdf`), with the same content as the Markdown and clickable links. Link to it directly ("Export PDF"). It returns `409` while the run is still running and takes a few seconds to generate. Keep the "Print" button too.

---

## 4. Polling rules

| What | Endpoint | Interval | Stop when |
|---|---|---|---|
| Ingest progress | `GET /collections/{id}/sources` | 3 s | no source is `queued`, `transcribing` or `analyzing` |
| Bank run | `GET /bank-runs/{id}` | 2 s | `status` is `done` or `failed` |

Start polling right after `POST /sync` or `POST /question-banks/{id}/run`, and when a page opens while work is still in progress. Pause polling while the browser tab is hidden (`document.visibilityState`).

---

## 5. Enums

| Name | Values |
|---|---|
| Source `type` | `youtube`, `web`, `audio`, `pdf` |
| Source `status` | `queued`, `transcribing`, `analyzing`, `ready`, `failed` |
| Sync `action` | `queued`, `skipped`, `failed`, `archived`, `feed` |
| `priority` | `high`, `normal`, `low` |
| `coverage` | `strong`, `partial`, `none` |
| Bank run `status` | `running`, `done`, `failed` |
| Report item `status` | `pending`, `done`, `failed` |

## 6. Formatting helpers
- **Time labels:** citations already include `label`: "12:00–13:00" for video and audio, the heading for web, "Page 3" for PDF. For segment and chapter times on the source page, format seconds as `m:ss`, or `h:mm:ss` when an hour or longer.
- **Dates:** show `published_at` as-is; `null` means "date unknown".
- **Link formats** (`deep_link`):

  | Type | Format |
  |---|---|
  | youtube | `https://youtu.be/<id>?t=<s>` |
  | audio | `<audio file>#t=<s>` (the browser starts playback there) |
  | web | `<url>#:~:text=<first words>` |
  | pdf | `<pdf>#page=<n>` |

  `app_link` is `/sources/<id>?t=<s>` for youtube and audio (plays in the app) and `/sources/<id>#seg-<id>` for web and pdf.
- **Sources that disappear:** archived sources never appear in answers. Their old citations in saved notes still work, because the links point at stored data.

## 7. Mapping to the PRD's suggested contract

| PRD §6 | This contract |
|---|---|
| `POST /sync?collection=yale` → sync log | same |
| `GET /collections` | same |
| `GET /collections/{id}/sources`, `GET /sources/{id}` | same |
| `POST /collections/{id}/ask` (question, filters) → answer, citations[] | same, plus `history` for follow-ups and `not_covered`/`closest`/warnings |
| `POST /collections/{id}/question-banks/run` (questions[]) → report | split into *save* (`POST …/question-banks`) and *run* (`POST /question-banks/{id}/run` → poll `GET /bank-runs/{id}`), because a 10-question run takes longer than one HTTP request should wait |
