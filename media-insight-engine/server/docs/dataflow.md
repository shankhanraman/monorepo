# Data flow

> Status: **Day 1 built**. Related docs: [architecture.md](architecture.md) · [datamodels.md](datamodels.md) · [api-contract.md](api-contract.md).

The system has **two paths that share one store** (PRD §5):

```mermaid
flowchart LR
    subgraph ingest["Ingest path: background, once per source"]
        direction LR
        S1["Sources<br/>YouTube, web page"] --> S2["Transcript<br/>captions / page text"]
        S2 --> S3["Segments<br/>60 s slices or sections"]
        S3 --> S4["Analyze through the Lens<br/>overview, chapters, summaries, tags, quotes"]
        S4 --> S5["Embed"]
    end
    LENS["Lens<br/>domain, role, focus, tags"] -.-> S4
    LENS -.-> Q3
    S5 --> DB[("Postgres + pgvector")]
    subgraph query["Query path: on demand"]
        direction LR
        Q1["Ask<br/>question or bank"] --> Q2["Retrieve<br/>vector + keyword, filters"]
        Q2 --> Q3["Answer<br/>cites every claim"]
        Q3 --> Q4["Finalize<br/>check citations, staleness,<br/>or 'not covered'"]
        Q4 --> Q5["Report / export"]
    end
    DB --> Q2
```

The sections below follow one piece of data through each flow, in the order AJ uses the app.

---

## 1. Sync: config file → sources (FR-1)

Triggered by `make sync COLLECTION=yale` (CLI) or the **Sync** button (`POST /sync?collection=yale`). Both run the same service.

```mermaid
sequenceDiagram
    autonumber
    actor AJ
    participant C as client
    participant API as server (sync service)
    participant F as config/ files
    participant DB as Postgres
    participant W as worker pool

    AJ->>C: click Sync
    C->>API: POST /sync?collection=yale
    API->>API: take the per-collection sync lock (busy → 409)
    API->>F: read yale.yaml + its lens file
    API->>API: validate (file broken → 422), build effective Lens
    API->>API: normalize every URL, detect its type
    API->>DB: upsert collections row (lens_text, lens_tags)
    API->>DB: load existing sources of yale
    API->>API: diff the file against the database
    API->>DB: insert new sources (status=queued), reset failed ones to queued,<br/>refresh labels and priorities, set archived on removed ones
    API->>DB: insert sync_logs row
    API->>W: submit every queued source id
    API-->>C: 200 sync log (queued / skipped / failed / archived + reasons)
    C->>C: show the log, start polling the sources list every 3 s
```

How each URL is decided:

| In the file? | In the database? | Current state | Action | Log reason |
|---|---|---|---|---|
| yes | no | — | insert, `queued` | "New URL" |
| yes | yes | `ready` | nothing | "Already ready" |
| yes | yes | `queued` / `transcribing` / `analyzing` | nothing | "Already being ingested (…)" |
| yes | yes | `failed` | reset to `queued` | "Retrying (last error: …)" |
| yes | yes | `archived` | un-archive, then the rows above | "Restored" + state |
| no | yes | not archived | `archived = true` | "Removed from yale.yaml" |
| yes, but invalid | — | — | nothing | the validation message |
| yes, Day-2 type | — | — | nothing | "Type 'audio' is not supported until Day 2" |

Because of these rules, running sync twice in a row gives "skipped" for everything (AC-9). Nothing is deleted, and nothing is left out of the log (FR-1.4).

The CLI variant does the same, then waits for its queued sources to finish and prints a line per source with the time it took. That's how AC-1 ("ready in under 5 minutes each") is measured.

---

## 2. Ingest: one source → ready (FR-2, FR-3)

Each queued source runs in a worker thread. Every step writes its result before moving on, so the status the UI polls is always true.

```mermaid
sequenceDiagram
    autonumber
    participant W as worker
    participant DB as Postgres
    participant YT as YouTube
    participant WEB as web page (Crawl4AI)
    participant AI as Claude Opus 5.5
    participant E as fastembed (local)

    W->>DB: status = transcribing
    alt type = youtube
        W->>YT: metadata (yt-dlp, no download): title, channel, date, duration
        W->>YT: captions (manual English first, else auto-generated)
        Note over W: no captions → failed "No captions available (audio transcription is Day 2)"
        W->>W: bucket caption lines into 60 s segments (keep raw text + lines)
    else type = web
        W->>WEB: render page in headless Chromium → clean Markdown + metadata
        Note over W: under ~150 words → failed "Page had no readable text"
        W->>W: split Markdown at headings into sections (long ones split again)
    end
    W->>DB: one transaction: delete old segments of this source, insert new ones,<br/>save metadata, status = analyzing
    W->>AI: Lens + numbered segments (prompts/analyze.md), structured output
    AI-->>W: overview, chapters (segment ranges), segment summaries + tags, key quotes
    W->>W: check output: chapter ranges → seconds, drop unknown tags,<br/>keep only quotes found verbatim, find each quote's exact second
    W->>E: embed (segment text + summary), batched
    E-->>W: 384-d vectors
    W->>DB: one transaction: overview, chapters, summaries, tags, quotes, embeddings,<br/>status = ready, ingested_at = now
```

What a 35-minute YouTube video becomes (AC-2):

| Item | Count | Example |
|---|---|---|
| Source row | 1 | title, channel, `published_at`, `duration_s = 2112` |
| Segments | ~35 | `720–780 s`, raw text, "Officers want the origin of the interest…", `[essays, why-major]` |
| Chapters | 3–8 | `570–1065 s` "Supplemental essays" |
| Key quotes | ≤ 10 | `731 s` "we really want to hear what got you curious…" (verbatim) |
| Embeddings | ~35 | one per segment |

Failures at any step set `status = failed` with a readable `error` and stop that source only. The next sync retries it. If the server restarts mid-job, startup sets the source back to `queued` and resubmits it.

---

## 3. Looking at a source (FR-3.6)

`GET /sources/12` reads `sources` plus its segments, chapters and quotes. It computes `deep_link` per segment and quote.

On the source page, the client:
- embeds the YouTube player using `ext_id`;
- seeks to `?t=` on load;
- makes every chapter, timeline row and quote call `player.seekTo(start_s)` when clicked (AC-3: within ±5 s).

Web sources render as sections with `id="seg-<id>"`.

---

## 4. Ask: question → grounded answer (FR-4)

`POST /collections/yale/ask` runs the **Q&A graph** (LangGraph).

```mermaid
flowchart LR
    IN((question)) --> R["retrieve<br/>vector top-30 + keyword top-30<br/>→ RRF → top 10"]
    R --> A["answer<br/>Sonnet 5.5, low effort<br/>structured: coverage, answer_md, conflicts"]
    A -->|"coverage strong / partial<br/>or already retried"| FIN["finalize (code)<br/>validate [n], build citations,<br/>staleness, not-covered"]
    A -->|"coverage none<br/>and first attempt"| RW["rewrite_query<br/>Sonnet 5.5: better search terms"]
    RW --> R
    FIN --> OUT((response))
```

```mermaid
sequenceDiagram
    autonumber
    actor AJ
    participant C as client
    participant G as Q&A graph (server)
    participant DB as Postgres
    participant E as fastembed
    participant AI as Claude Sonnet 5.5

    AJ->>C: "What does Yale look for in the why-this-major short answer?"
    C->>G: POST /collections/yale/ask {question, history, filters}
    G->>E: embed (previous question + this question)
    G->>DB: vector search + full-text search<br/>WHERE collection_id='yale' AND status='ready' AND NOT archived<br/>AND filters (sources, tags, dates)
    DB-->>G: candidates → merged by rank → top 10 segments
    G->>AI: Lens + history + segments numbered [1]…[10] (prompts/answer.md)
    AI-->>G: {coverage, answer_md with [n], conflicts}
    opt coverage none on the first attempt
        G->>AI: rewrite the search query
        G->>DB: retrieve again with the new query
        G->>AI: answer again
    end
    G->>G: finalize: drop [n] not in the list, renumber, build citations + links,<br/>stale if published > 18 months ago or unknown,<br/>no valid [n] left → "Not covered in your sources" + closest 3
    G->>DB: insert answers row (citations snapshot, model, latency)
    G-->>C: AskResponse
    C->>C: render [n] links, citation cards, coverage badge, warnings
```

How the outcomes map to acceptance checks:

| Situation | Result | AC |
|---|---|---|
| Sources answer it | answer with ≥ 2 citations, each opening the right moment | AC-4 |
| Cited video older than 18 months | `stale_warning`: verify on the official site; date shown on every citation | AC-5 |
| Sources don't cover it | "Not covered in your sources", plus closest moments; no invented answer | AC-6 |
| A web page was added and synced | its sections can be retrieved and cited with a `#:~:text=` link | AC-7 |
| Asked in Yale while MIT is also synced | the `collection_id = 'yale'` filter means MIT can't appear | AC-10 |

Follow-up questions: the client sends `history`. The graph uses the previous question in the search and the earlier turns in the answer prompt. The server keeps no session.

**Save to notes:** `POST /notes` stores the question, the answer and the citation snapshot as they are.

---

## 5. Question bank: many questions → report (FR-5)

```mermaid
sequenceDiagram
    autonumber
    actor AJ
    participant C as client
    participant API as server
    participant P as worker pool (4 at a time)
    participant G as Q&A graph
    participant DB as Postgres

    AJ->>C: paste 10 questions (or upload .txt / .csv)
    C->>C: one per line / CSV first column, trim, drop empty + duplicates
    C->>API: POST /collections/yale/question-banks {name, questions}
    API->>DB: insert question_banks
    API-->>C: 201 bank (id 3)
    AJ->>C: Run
    C->>API: POST /question-banks/3/run
    API->>DB: insert bank_runs (running, done 0, total 10) + 10 pending answers rows
    API->>P: submit 10 questions
    API-->>C: 202 run (id 7)
    loop every 2 s until done
        C->>API: GET /bank-runs/7
        API-->>C: done / total + finished items
    end
    par up to 4 questions at once
        P->>G: run the Q&A graph for question i
        G-->>P: AskResponse
        P->>DB: update answers row i (done or failed), bank_runs.done + 1
    end
    P->>DB: bank_runs status = done, finished_at
    AJ->>C: Export Markdown
    C->>API: GET /bank-runs/7/report.md
    API-->>C: file download
```

Each report item is built like this (FR-5.3):
- **short answer:** the `answer_md` of that question;
- **watch these:** the cited segments in retrieval order, at most 5. Fewer appear only when fewer were cited, and "not covered" questions show none;
- **coverage:** strong / partial / none.

One failed question is marked `failed` with its error and does not stop the run. The Markdown export lists every question with its answer, coverage and timestamp links (AC-8). For PDF on Day 1, the browser's print dialog saves the report page.

---

## 6. Golden test set (AC-11)

`python -m app.golden yale` reads `golden/yale.yaml`, which AJ fills in with 10 questions, each with an expected source URL and timestamp plus a tolerance. For each question it:
1. runs the same Q&A graph;
2. checks whether any citation is the expected source within the tolerance;
3. prints a table and the score.

The target is ≥ 8 of 10. Run it after every prompt, segment-size or retrieval change. The PRD says to tune retrieval before rewording prompts.

---

## 7. Where each kind of data is written

| Step | Writes |
|---|---|
| Sync | `collections` (upsert), `sources` (insert / reset / archive / refresh labels), `sync_logs` |
| Ingest: transcript | `sources` metadata + status, `segments` (raw text, times, caption lines) |
| Ingest: analysis + embed | `sources.overview`, `chapters`, `segments.summary/tags/embedding`, `key_quotes`, status `ready` |
| Ask | `answers` (chat answer, `run_id` null) |
| Bank | `question_banks`, `bank_runs`, `answers` (one per question) |
| Notes | `notes` |

Nothing is ever hard-deleted by sync. The only deletes are explicit user actions (delete note, delete bank), plus replacing a failed source's segments when it is retried.

## 8. Failure handling at a glance

| Failure | Seen as | Recovery |
|---|---|---|
| Bad YAML file | `POST /sync` → 422 with file and field | fix the file, sync again |
| Bad source entry | `failed` line in the sync log | fix the entry, sync again |
| No captions / blocked / page empty | source `failed` + reason | Day 2 audio, or replace the URL |
| Model error after retries / refusal | source `failed`, or answer "not covered" with reason | sync again (retries failed sources) / ask again |
| Server restart mid-ingest | source stays `transcribing`/`analyzing` until startup re-queues it | automatic |
| Bank question fails | that item `failed` + error, run continues | run the bank again |
| Two syncs at once | second gets 409 | wait, retry |
