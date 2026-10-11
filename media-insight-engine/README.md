# Admissions Media Insight Engine (Day 1 + Day 2)

Turns admissions videos, podcasts, web pages and PDFs into a timestamped knowledge base and answers questions **only from those sources**, with links to the exact minute or paragraph. Requirements: [docs/Admissions Media Insight Engine — Product Requirements.pdf](docs/).

| | |
|---|---|
| Design | [architecture](server/docs/architecture.md) · [data models](server/docs/datamodels.md) · [data flow](server/docs/dataflow.md) |
| API | [api-contract.md](server/docs/api-contract.md) (guide) · [openapi.yaml](server/docs/openapi.yaml) (contract) · live docs at http://localhost:8003/docs |
| Stack | FastAPI (Python 3.12) · React + TypeScript + Vite · Postgres 17 + pgvector · Claude Opus 5.5 (analysis) / Sonnet 5.5 (answers) · LangGraph (Q&A loop) · Crawl4AI (web pages) · fastembed (local embeddings) · faster-whisper (podcast speech-to-text) · pypdf |

## Run it

Prerequisite: Docker Desktop, running.

```bash
cp .env.example .env            # Windows: Copy-Item .env.example .env
#   then put your Anthropic key in .env: ANTHROPIC_API_KEY=sk-ant-...
docker compose up --build -d    # first build ~15 min (Chromium, embedding model, 1.6 GB speech-to-text model)
```
Open **http://localhost:5176**.

| Port (localhost only) | What |
|---|---|
| 5176 | web app |
| 8003 | API (`/docs` for Swagger) |
| 5437 | Postgres |

## Add sources and sync (PRD FR-1)

Edit one file per college in [config/collections/](config/collections/) (`yale.yaml`, `mit.yaml`, …). The shared Lens is in [config/lenses/](config/lenses/).

```yaml
sources:
  - url: https://www.youtube.com/watch?v=VIDEO_ID
    label: Admissions podcast – supplemental essays
    priority: high
  - url: https://admissions.yale.edu/essay-topics
  - url: https://oir.example.edu/common-data-set-2025-2026.pdf     # PDF (one section per page)
  - url: https://feeds.example.com/inside-yale-admissions          # podcast RSS feed
    type: rss
    episodes: 3               # newest N episodes (default 10)
    match: "essay|testing"    # optional: only episodes whose title matches
```
Then sync, either with the **Sync** button on the Sources page or from a terminal:
```bash
make sync COLLECTION=yale
# Windows (no make):
docker compose exec server python -m app.sync yale
```
- Sync prints a line for every URL (queued / skipped / failed / archived, with the reason), then follows the ingest until each source is `ready` or `failed`, with timings.
- Running it again only ingests new or previously failed URLs.
- URLs removed from the file are archived, never deleted.
- Config files are mounted into the container, so there's no rebuild after editing them.

**Supported sources:**
- YouTube videos: captions, or speech-to-text when a video has none;
- web pages;
- PDFs (text PDFs; scanned ones are rejected);
- podcasts: an RSS feed (each selected episode becomes its own source), a direct MP3/M4A link, or a podcast page such as Apple Podcasts.

Spotify links are rejected (DRM); use the show's RSS feed instead.

**Podcasts take a while.** Speech-to-text runs locally with faster-whisper `large-v3-turbo` (best accuracy on names and numbers): about **12–20 minutes for a 35-minute episode**, one episode at a time. The Sources page shows "transcribing 42 %". For faster results, set `WHISPER_MODEL=small.en` in `.env` (about 5 min per episode, less accurate) and run `docker compose up -d`. Audio files are deleted right after transcription.

## Tune without redeploying
- **Lens** (domain, reader, focus, tags, segment length, staleness age): `config/lenses/*.yaml`. Re-sync to store it. It applies to sources analyzed from then on.
- **Prompts:** `prompts/analyze.md`, `prompts/answer.md` and `prompts/rewrite.md`. They're re-read on every call.

## Tests
```bash
make test        # or: docker compose exec server pytest -q
cd client && npm test && npm run build
```
- **Server:** 50 tests. They cover:
  - config, URLs, segmenting, sync rules and the analysis checks;
  - citation validation, staleness and not-covered;
  - the Q&A graph's routing, and the Markdown report;
  - a contract test (server routes = `openapi.yaml`);
  - database integration (sync idempotency, Yale/MIT isolation, endpoints).

  Claude is faked in tests.
- **Client:** 22 tests, for the `[n]` renderer, the question-list parser and time formatting.

**Golden set (AC-11):** fill [golden/yale.yaml](golden/yale.yaml) with 10 questions and the moment that should be cited, then run `make golden COLLECTION=yale` (Windows: `docker compose exec server python -m app.golden yale`). The target is ≥ 8/10.

## Decisions taken where the PRD left questions open
| Open question (PRD §8) | Day-1 default |
|---|---|
| Hosting | local laptop, no auth (all ports bound to 127.0.0.1) |
| Segment length | 60 s minute summaries (`segment_seconds` in the lens; 30–300) |
| Aksh's login / notes | shares AJ's notes (single user) |
| Day-1 demo question | "What does Yale look for in the why-this-major short answer?" |
| Golden test set | template in `golden/yale.yaml`, for AJ to fill |

Deliberate deviation from the PRD: the Q&A step uses a small **LangGraph** graph (retrieve → answer → one rewrite-and-retry when the sources don't cover it → finalize), although the PRD says "no agent frameworks on Day 1". The choice is recorded in [architecture.md](server/docs/architecture.md) (D7).

## Known limits
- One analysis call per source handles about 150 segments (~2.5 h of video). Longer sources need chunking.
- Web pages are crawled one at a time (Crawl4AI's SQLite cache can't handle parallel crawls).
- Podcasts miss the PRD's 5-minute target with `large-v3-turbo` on CPU (see above); one transcription runs at a time.
- Scanned PDFs (no text layer) are rejected; there is no OCR.
- New podcast episodes are picked up when you sync again; there is no scheduled sync (PRD Week 2+).
- Background work runs inside the API process, so run a single server replica.
- If YouTube changes something and captions or metadata start failing, update `yt-dlp` / `youtube-transcript-api` in `server/requirements.txt` and rebuild.
- Personal research use only: transcripts stay in the local database (PRD §8, terms of use).
