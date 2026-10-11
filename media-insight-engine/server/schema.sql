-- Applied at every server start; must stay idempotent. See docs/datamodels.md.
-- ponytail: still no migration tool; Day-2 columns are added with idempotent ALTERs below.
-- Switch to Alembic when a change can't be expressed that way (renames, data migrations).
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS collections (
    id                 text PRIMARY KEY,
    name               text NOT NULL,
    lens_name          text NOT NULL,
    lens_text          text NOT NULL,
    lens_tags          text[] NOT NULL DEFAULT '{}',
    focus_note         text,
    segment_seconds    int NOT NULL CHECK (segment_seconds BETWEEN 30 AND 300),
    stale_after_months int NOT NULL DEFAULT 18,
    last_synced_at     timestamptz,
    created_at         timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sources (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    collection_id  text NOT NULL REFERENCES collections(id),
    type           text NOT NULL CHECK (type IN ('youtube', 'web', 'audio', 'pdf')),
    url            text NOT NULL,
    ext_id         text,
    label          text,
    priority       text NOT NULL DEFAULT 'normal' CHECK (priority IN ('high', 'normal', 'low')),
    notes          text,
    title          text,
    host           text,
    published_at   date,
    duration_s     int,
    status         text NOT NULL DEFAULT 'queued'
                   CHECK (status IN ('queued', 'transcribing', 'analyzing', 'ready', 'failed')),
    error          text,
    archived       boolean NOT NULL DEFAULT false,
    overview       text,
    analysis_model text,
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now(),
    ingested_at    timestamptz,
    UNIQUE (collection_id, url)
);

CREATE TABLE IF NOT EXISTS segments (
    id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_id bigint NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    ord       int NOT NULL,
    start_s   int NOT NULL,
    end_s     int NOT NULL,
    anchor    text,
    text      text NOT NULL,
    summary   text,
    tags      text[] NOT NULL DEFAULT '{}',
    embedding vector(384),
    snippets  jsonb,
    tsv       tsvector GENERATED ALWAYS AS (
                  to_tsvector('english', text || ' ' || coalesce(summary, ''))) STORED,
    UNIQUE (source_id, ord)
);
-- Day 2: podcast audio + PDF sources, transcription progress, RSS feed origin, playable audio URL.
-- Idempotent ALTERs so databases created on Day 1 keep their data.
ALTER TABLE sources ADD COLUMN IF NOT EXISTS progress int CHECK (progress BETWEEN 0 AND 100);
ALTER TABLE sources ADD COLUMN IF NOT EXISTS feed_url text;
ALTER TABLE sources ADD COLUMN IF NOT EXISTS media_url text;
ALTER TABLE sources DROP CONSTRAINT IF EXISTS sources_type_check;
ALTER TABLE sources ADD CONSTRAINT sources_type_check CHECK (type IN ('youtube', 'web', 'audio', 'pdf'));
CREATE INDEX IF NOT EXISTS sources_feed_idx ON sources (feed_url) WHERE feed_url IS NOT NULL;

CREATE INDEX IF NOT EXISTS segments_embedding_idx ON segments USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS segments_tsv_idx ON segments USING gin (tsv);
CREATE INDEX IF NOT EXISTS segments_tags_idx ON segments USING gin (tags);

CREATE TABLE IF NOT EXISTS chapters (
    id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_id bigint NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    ord       int NOT NULL,
    start_s   int NOT NULL,
    end_s     int NOT NULL,
    title     text NOT NULL,
    summary   text NOT NULL
);
CREATE INDEX IF NOT EXISTS chapters_source_idx ON chapters (source_id, ord);

CREATE TABLE IF NOT EXISTS key_quotes (
    id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_id  bigint NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    segment_id bigint NOT NULL REFERENCES segments(id) ON DELETE CASCADE,
    ts_s       int NOT NULL,
    quote      text NOT NULL,
    is_advice  boolean NOT NULL DEFAULT false
);
CREATE INDEX IF NOT EXISTS key_quotes_source_idx ON key_quotes (source_id);

CREATE TABLE IF NOT EXISTS sync_logs (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    collection_id text NOT NULL REFERENCES collections(id),
    created_at    timestamptz NOT NULL DEFAULT now(),
    summary       jsonb NOT NULL,
    entries       jsonb NOT NULL
);

CREATE TABLE IF NOT EXISTS question_banks (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    collection_id text NOT NULL REFERENCES collections(id),
    name          text NOT NULL,
    questions     text[] NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS bank_runs (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    bank_id     bigint NOT NULL REFERENCES question_banks(id) ON DELETE CASCADE,
    status      text NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'done', 'failed')),
    done        int NOT NULL DEFAULT 0,
    total       int NOT NULL,
    filters     jsonb NOT NULL DEFAULT '{}',
    created_at  timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz
);
-- One running run per bank (the API answers 409 otherwise).
CREATE UNIQUE INDEX IF NOT EXISTS bank_runs_one_running ON bank_runs (bank_id) WHERE status = 'running';

CREATE TABLE IF NOT EXISTS answers (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    collection_id text NOT NULL,          -- slug or 'all', so no foreign key
    run_id        bigint REFERENCES bank_runs(id) ON DELETE CASCADE,
    item_index    int,
    question      text NOT NULL,
    status        text NOT NULL DEFAULT 'done' CHECK (status IN ('pending', 'done', 'failed')),
    answer_md     text,
    coverage      text CHECK (coverage IN ('strong', 'partial', 'none')),
    citations     jsonb NOT NULL DEFAULT '[]',
    closest       jsonb NOT NULL DEFAULT '[]',
    watch         jsonb NOT NULL DEFAULT '[]',
    stale_warning text,
    conflicts     text,
    error         text,
    retried       boolean NOT NULL DEFAULT false,
    model         text,
    latency_ms    int,
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS answers_run_idx ON answers (run_id, item_index);

CREATE TABLE IF NOT EXISTS notes (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    collection_id text NOT NULL,
    question      text NOT NULL,
    answer_md     text NOT NULL,
    coverage      text NOT NULL CHECK (coverage IN ('strong', 'partial', 'none')),
    citations     jsonb NOT NULL DEFAULT '[]',
    comment       text,
    created_at    timestamptz NOT NULL DEFAULT now()
);
