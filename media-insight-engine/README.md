# Admissions Media Insight Engine (Day 1 + Day 2)

Turns admissions videos, podcasts, web pages and PDFs into a timestamped knowledge base and answers questions **only from those sources**, with links to the exact minute or paragraph. Requirements: [docs/Admissions Media Insight Engine — Product Requirements.pdf](docs/).

| | |
|---|---|
| Design | [architecture](server/docs/architecture.md) · [data models](server/docs/datamodels.md) · [data flow](server/docs/dataflow.md) |
| API | [api-contract.md](server/docs/api-contract.md) (guide) · [openapi.yaml](server/docs/openapi.yaml) (contract) · live docs at http://localhost:8003/docs |
| MCP | [mcp.md](server/docs/mcp.md) — tools + agents over Model Context Protocol at http://localhost:8003/mcp |
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

## Run it on Kubernetes (Helm, local dev)

For a kind cluster instead of Compose. The chart ([charts/mie/](charts/mie/)) reproduces the
full stack — Vault + mutual-TLS Postgres, server, client — and is **local-dev only** (dev Vault,
no TLS ingress, no HA). Design: [docs/superpowers/specs/2026-10-24-helm-chart-design.md](docs/superpowers/specs/2026-10-24-helm-chart-design.md).

Prerequisites: a running kind cluster with a `localhost:5000` registry, plus `helm` and `kubectl`.

```bash
# 1. secrets (gitignored) — copy the example and fill in your Anthropic key + a DB password
cp charts/mie/values-local.yaml.example charts/mie/values-local.yaml

# 2. build the app images and push them to the local registry
make helm-images

# 3. install (runs helm-sync to copy config/prompts/golden into the chart, then helm upgrade --install)
make helm-install

# 4. reach the UI
kubectl port-forward svc/mie-mie-client 8080:80   # then open http://localhost:8080
```

`make helm-lint` renders the chart without a cluster (`helm lint` + `helm template`). Sync a
collection with `kubectl exec deploy/mie-mie-server -- python -m app.sync yale`. Vault runs in
dev mode (in-memory): if its pod restarts, re-run the `cert-init` Job — see the install `NOTES`.

**Windows (no `make`):** the chart's `files/` are committed, so you can skip `helm-sync` and run
helm directly: `helm upgrade --install mie charts/mie -f charts/mie/values-local.yaml` (build/push
the images first with the two `docker build … && docker push …` lines from the `helm-images` target).

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

**Podcasts take a while.** Speech-to-text runs locally with faster-whisper `large-v3-turbo` (best accuracy on names and numbers): measured at about **2× the episode length** (a 37-minute episode took 1 h 15 min from Sync to ready), one episode at a time. The first podcast after a server start also waits ~3 min while the model loads; the audio download itself takes seconds. The Sources page shows "transcribing 42 %". For faster results, set `WHISPER_MODEL=small.en` in `.env` (several times faster, less accurate) and run `docker compose up -d`. Audio files are deleted right after transcription.

**Use the GPU.** The server picks its speech-to-text backend from the machine (`WHISPER_DEVICE=auto`, or force `mlx` / `cuda` / `cpu`). `curl localhost:8003/health` shows which one it chose (`"whisper": "..."`).

| Machine | Start with | Backend |
|---|---|---|
| Any (default) | `make up` | faster-whisper on CPU (the timings above) |
| NVIDIA GPU + [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/) | `make up-gpu` | faster-whisper on CUDA |
| Apple Silicon Mac | `make dev-mac`, then `make sync-mac COLLECTION=yale` | mlx-whisper on the Apple GPU |

Docker on macOS can't reach the Mac GPU, so `make dev-mac` keeps Postgres and the client in Docker and runs the server natively. One-time setup: `brew install ffmpeg`, then in `server/`: `python3.12 -m venv .venv && .venv/bin/pip install -r requirements-mac.txt && .venv/bin/crawl4ai-setup`. On the Mac backend the Sources page shows 0 % until each episode finishes (mlx-whisper reports no progress).

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

## CI/CD
[.github/workflows/media-insight-engine.yml](../.github/workflows/media-insight-engine.yml) runs on every PR and push that touches this folder:

| Job | When | What |
|---|---|---|
| `server` | always | `pytest` against a throwaway pgvector Postgres (password auth, no Vault) |
| `client` | always | `npm test` + `npm run build` (typecheck + Vite build) |
| `publish` | push to `main`, after both pass | builds and pushes `ghcr.io/shankhanraman/mie-server` and `mie-client` (tags: commit SHA and `latest`) |

The golden set isn't run in CI (it needs `ANTHROPIC_API_KEY`). The `mie-client` image is the production build: nginx serves the app and proxies `/api/*` to a service named `server` on port 8003. Local `docker compose` still builds the dev target. GHCR packages are private by default: change it under the repo owner's **Packages → Package settings**.

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
- Recreating the server container (`docker compose up --build`, or `up` after changing `.env`) restarts a running transcription from 0 %. Rebuild when nothing is transcribing.
- `av` (PyAV) is pinned to 18.1.0 because PyAV 19 breaks faster-whisper 1.2.1; see architecture.md §9.
- Scanned PDFs (no text layer) are rejected; there is no OCR.
- New podcast episodes are picked up when you sync again; there is no scheduled sync (PRD Week 2+).
- Background work runs inside the API process, so run a single server replica.
- If YouTube changes something and captions or metadata start failing, update `yt-dlp` / `youtube-transcript-api` in `server/requirements.txt` and rebuild.
- Personal research use only: transcripts stay in the local database (PRD §8, terms of use).
