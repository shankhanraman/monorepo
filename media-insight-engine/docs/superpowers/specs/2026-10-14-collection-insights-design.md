# Collection Insights — design

Date: 2026-10-14
Status: approved (direction validated via visual mockup)

## Goal

A collection-wide **analytical agent** that reads across *all* ready sources in a college and
produces grounded, cross-cutting insights, shown on a new **home page** as a split layout:

- **Left — Findings:** a masonry grid of insight cards.
- **Right — The Atlas:** a quantitative dashboard (consensus gauge, topic-coverage bars, source timeline).

This layers on top of the existing *per-source* analysis (overview / chapters / segments / key quotes);
it does not replace it.

## Card types (insight kinds)

1. **theme** — recurring topic / consensus advice several sources agree on.
2. **contradiction** — sources give conflicting guidance (ideally ≥2 sources).
3. **trend** — emphasis that shifts by publish date (e.g. only in recent sources).
4. **gap** — a Lens tag that sources barely cover (few or zero sources).

Every insight cites its supporting sources (source-level, in-app links to `/sources/{id}`),
consistent with the product's "only from sources" principle.

## Trigger & storage

- **Auto after every sync.** Synthesis is expensive and needs sources to be `ready`, so it runs
  when a collection's ingest **drains** (no sources left `queued`/`transcribing`/`analyzing`),
  triggered from the end of `ingest_source`. A re-sync where everything is already ready also
  triggers it directly (nothing to drain).
- A single-thread executor runs it; a per-collection guard prevents concurrent/duplicate runs.
- The latest result is stored in a new `collection_analyses` table (one row per collection, replaced each run).
- The result carries a **stale** flag (true if the collection was synced, or any source re-ingested,
  after the analysis was generated).

## Deterministic vs model-generated

To keep the Atlas trustworthy, the quantitative parts are computed in Python, not by the LLM:

- **coverage** — per Lens tag, the count of distinct ready sources with ≥1 segment carrying that tag.
  Tags with 0–1 sources are flagged as gaps.
- **timeline** — ready sources grouped by `year(published_at)` (plus an "undated" bucket).
- **consensus** — `round(100 * themes / (themes + contradictions))` over the produced insights
  (100 when there are no contradictions), a defensible, explainable number.

The **LLM** produces only the qualitative `insights[]`. Its input per source is a compact digest:
id, title, date, type, overview, chapter titles+summaries, and key quotes — not every segment,
so the whole collection fits one call. Output is structured (schema-validated) and checked server-side:
`source_ids` are filtered to the ready set; theme/contradiction/trend need ≥1 valid source,
gaps may have none.

## Backend changes

- `server/schema.sql` — new idempotent `collection_analyses` table.
- `prompts/synthesize.md` — new prompt (re-read per call, like `analyze.md`).
- `server/app/services/insights.py` — build digest, deterministic coverage/timeline/consensus,
  LLM call via `llm.parse`, validation, persistence (`run(collection_id)`).
- `server/app/services/jobs.py` — `submit_synthesis(collection_id)` on a dedicated 1-thread pool
  with a per-collection lock.
- `server/app/services/ingest.py` — after each source finishes, if the collection has no more
  in-progress sources, `submit_synthesis`.
- `server/app/services/sync.py` — after commit, if nothing was queued, `submit_synthesis`.
- `server/app/routers/collections.py` — `GET /collections/{collection_id}/insights`
  returns `CollectionAnalysis` (status `ready`/`running`/`failed`/`empty`, insights, coverage,
  timeline, stats, consensus, generated_at, stale). 200 with `status:"empty"` when never run.
- `server/app/models/api.py` — `Insight`, `InsightCitation`, `CoverageTopic`, `TimelineBucket`,
  `CollectionAnalysis`.
- `server/docs/openapi.yaml` — add the new path (required by the contract test) and schemas.

## Frontend changes

- `client/src/types.ts` — mirror the new API types.
- `client/src/api.ts` — `getCollectionInsights(collectionId)`.
- `client/src/features/insights/` — `InsightsPage.tsx` (split layout, polls every 3 s while
  `running`), `InsightCard.tsx`, `Atlas.tsx` (gauge + coverage bars + timeline), `insights.css`
  (matches the editorial theme: masonry via CSS columns, color-coded by kind).
- `client/src/App.tsx` — add "Insights" as the first nav item; collection index route and the
  Home redirect go to `insights` instead of `sources`.

## Testing

- Server: unit-test the pure functions (coverage counting, timeline bucketing, consensus,
  insight validation/`check`) and the drain-trigger decision; extend the contract test is automatic
  (path added to `openapi.yaml`). DB/LLM integration follows existing patterns but needs Docker.
- Client: `npm run build` (typecheck) and a small test for any pure helper.

## Out of scope (YAGNI)

- Segment-level deep links inside insight cards (source-level links first; can enhance later).
- Manual "refresh insights" button (auto-after-sync covers it; trivial to add later).
- Historical/trend charts beyond the single timeline.
