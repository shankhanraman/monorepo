"""API schemas. These mirror docs/openapi.yaml (tests/test_contract.py checks the paths stay in sync)."""
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

SourceType = Literal["youtube", "web", "audio", "pdf"]
SourceStatus = Literal["queued", "transcribing", "analyzing", "ready", "failed"]
Coverage = Literal["strong", "partial", "none"]
Priority = Literal["high", "normal", "low"]


class SourceCounts(BaseModel):
    total: int
    ready: int
    in_progress: int
    failed: int
    archived: int


class Collection(BaseModel):
    id: str
    name: str
    lens_name: str
    lens_tags: list[str]
    focus_note: str | None
    segment_seconds: int
    source_counts: SourceCounts
    last_synced_at: datetime | None


class SyncEntry(BaseModel):
    url: str
    label: str | None
    action: Literal["queued", "skipped", "failed", "archived", "feed"]
    reason: str
    source_id: int | None
    feed_url: str | None = None  # Day-1 logs in the database don't have it


class SyncSummary(BaseModel):
    queued: int
    skipped: int
    failed: int
    archived: int


class SyncLog(BaseModel):
    id: int
    collection_id: str
    created_at: datetime
    summary: SyncSummary
    entries: list[SyncEntry]


class SourceSummary(BaseModel):
    id: int
    collection_id: str
    type: SourceType
    url: str
    label: str | None
    priority: Priority
    title: str | None
    host: str | None
    published_at: date | None
    duration_s: int | None
    status: SourceStatus
    error: str | None
    archived: bool
    ingested_at: datetime | None
    segment_count: int
    progress: int | None
    stale: bool
    feed_url: str | None


class Chapter(BaseModel):
    id: int
    start_s: int
    end_s: int
    title: str
    summary: str


class Segment(BaseModel):
    id: int
    ord: int
    start_s: int
    end_s: int
    anchor: str | None
    text: str
    summary: str | None
    tags: list[str]
    deep_link: str


class KeyQuote(BaseModel):
    id: int
    segment_id: int
    ts_s: int
    quote: str
    is_advice: bool
    deep_link: str


class SourceDetail(SourceSummary):
    ext_id: str | None
    media_url: str | None
    overview: str | None
    chapters: list[Chapter]
    segments: list[Segment]
    key_quotes: list[KeyQuote]


class AskFilters(BaseModel):
    source_ids: list[int] = []
    tags: list[str] = []
    date_from: date | None = None
    date_to: date | None = None


class HistoryTurn(BaseModel):
    question: str
    answer_md: str


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    history: list[HistoryTurn] = Field(default=[], max_length=10)
    filters: AskFilters = AskFilters()


class Citation(BaseModel):
    n: int
    segment_id: int
    source_id: int
    collection_id: str
    source_type: SourceType
    source_title: str
    host: str | None
    published_at: date | None
    start_s: int
    end_s: int
    anchor: str | None
    label: str
    snippet: str
    deep_link: str
    app_link: str
    stale: bool


class AskResponse(BaseModel):
    question: str
    label: Literal["Summary of sources"]
    answer_md: str
    coverage: Coverage
    not_covered: bool
    citations: list[Citation]
    closest: list[Citation]
    stale_warning: str | None
    conflicts: str | None
    retried: bool


class QuestionBankCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    questions: list[str] = Field(min_length=1, max_length=100)


class QuestionBank(BaseModel):
    id: int
    collection_id: str
    name: str
    questions: list[str]
    created_at: datetime
    latest_run_id: int | None


class RunRequest(BaseModel):
    filters: AskFilters = AskFilters()


class ReportItem(BaseModel):
    index: int
    question: str
    status: Literal["pending", "done", "failed"]
    answer_md: str | None
    coverage: Coverage | None
    watch: list[Citation]
    stale_warning: str | None
    error: str | None


class BankRun(BaseModel):
    id: int
    bank_id: int
    bank_name: str
    collection_id: str
    status: Literal["running", "done", "failed"]
    done: int
    total: int
    created_at: datetime
    finished_at: datetime | None
    items: list[ReportItem]


InsightKind = Literal["theme", "contradiction", "trend", "gap"]


class InsightCitation(BaseModel):
    source_id: int
    source_title: str
    source_type: SourceType
    published_at: date | None
    app_link: str


class InsightEvidence(BaseModel):
    source_id: int
    source_title: str
    source_type: SourceType
    quote: str
    role: Literal["supports", "opposes", "context"]
    app_link: str
    timestamp_s: int


class Insight(BaseModel):
    kind: InsightKind
    title: str
    detail: str
    tag: str | None
    sources: list[InsightCitation]
    evidence: list[InsightEvidence] = []
    confidence: Literal["high", "medium", "low"] = "medium"
    recommended_action: str | None = None


class CoverageTopic(BaseModel):
    tag: str
    sources: int
    gap: bool


class TimelineBucket(BaseModel):
    period: str
    sources: int


class CollectionAnalysis(BaseModel):
    collection_id: str
    status: Literal["ready", "running", "failed", "empty"]
    model: str | None
    source_count: int
    segment_count: int
    consensus: int | None
    insights: list[Insight]
    coverage: list[CoverageTopic]
    timeline: list[TimelineBucket]
    stale: bool
    error: str | None
    generated_at: datetime | None


class NoteCreate(BaseModel):
    collection_id: str
    question: str
    answer_md: str
    coverage: Coverage
    citations: list[Citation]
    comment: str | None = Field(default=None, max_length=2000)


class Note(NoteCreate):
    id: int
    created_at: datetime
