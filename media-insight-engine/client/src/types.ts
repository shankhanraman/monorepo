// Hand-written types matching server/docs/openapi.yaml (contract 0.2.0).

export type SourceType = 'youtube' | 'web' | 'audio' | 'pdf';
export type SourceStatus = 'queued' | 'transcribing' | 'analyzing' | 'ready' | 'failed';
export type Coverage = 'strong' | 'partial' | 'none';
export type Priority = 'high' | 'normal' | 'low';
export type SyncAction = 'queued' | 'skipped' | 'failed' | 'archived' | 'feed';

export interface SourceCounts {
  total: number;
  ready: number;
  in_progress: number;
  failed: number;
  archived: number;
}

export interface Collection {
  id: string;
  name: string;
  lens_name: string;
  lens_tags: string[];
  focus_note: string | null;
  segment_seconds: number;
  source_counts: SourceCounts;
  last_synced_at: string | null;
}

export interface SyncEntry {
  url: string;
  label: string | null;
  action: SyncAction;
  reason: string;
  /** Null when the entry failed validation, and for feed lines. */
  source_id: number | null;
  /** The RSS feed an episode came from; null otherwise. */
  feed_url: string | null;
}

export interface SyncLog {
  id: number;
  collection_id: string;
  created_at: string;
  summary: { queued: number; skipped: number; failed: number; archived: number };
  entries: SyncEntry[];
}

export interface SourceSummary {
  id: number;
  collection_id: string;
  type: SourceType;
  url: string;
  label: string | null;
  priority: Priority;
  title: string | null;
  host: string | null;
  published_at: string | null;
  duration_s: number | null;
  status: SourceStatus;
  error: string | null;
  archived: boolean;
  ingested_at: string | null;
  segment_count: number;
  /** 0–100 while `transcribing` (audio, or YouTube without captions); null otherwise. */
  progress: number | null;
  /** Older than the collection's stale_after_months (default 18), or date unknown. */
  stale: boolean;
  /** The RSS feed this episode came from. */
  feed_url: string | null;
}

export interface Chapter {
  id: number;
  start_s: number;
  end_s: number;
  title: string;
  summary: string;
}

export interface Segment {
  id: number;
  ord: number;
  start_s: number;
  end_s: number;
  anchor: string | null;
  text: string;
  summary: string;
  tags: string[];
  deep_link: string;
}

export interface KeyQuote {
  id: number;
  segment_id: number;
  ts_s: number;
  quote: string;
  is_advice: boolean;
  deep_link: string;
}

export interface SourceDetail extends SourceSummary {
  ext_id: string | null;
  /** Playable audio URL for the in-app player (audio sources); null otherwise. */
  media_url: string | null;
  overview: string | null;
  chapters: Chapter[];
  segments: Segment[];
  key_quotes: KeyQuote[];
}

export interface AskFilters {
  source_ids?: number[];
  tags?: string[];
  date_from?: string | null;
  date_to?: string | null;
}

export interface HistoryTurn {
  question: string;
  answer_md: string;
}

export interface AskRequest {
  question: string;
  history?: HistoryTurn[];
  filters?: AskFilters;
}

export interface Citation {
  n: number;
  segment_id: number;
  source_id: number;
  collection_id: string;
  source_type: SourceType;
  source_title: string;
  host: string | null;
  published_at: string | null;
  start_s: number;
  end_s: number;
  anchor: string | null;
  label: string;
  snippet: string;
  deep_link: string;
  app_link: string;
  stale: boolean;
}

export interface AskResponse {
  question: string;
  label: string;
  answer_md: string;
  coverage: Coverage;
  not_covered: boolean;
  citations: Citation[];
  closest: Citation[];
  stale_warning: string | null;
  conflicts: string | null;
  retried: boolean;
}

export interface QuestionBankCreate {
  name: string;
  questions: string[];
}

export interface QuestionBank {
  id: number;
  collection_id: string;
  name: string;
  questions: string[];
  created_at: string;
  latest_run_id: number | null;
}

export interface ReportItem {
  index: number;
  question: string;
  status: 'pending' | 'done' | 'failed';
  answer_md: string | null;
  coverage: Coverage | null;
  watch: Citation[];
  stale_warning: string | null;
  error: string | null;
}

export interface BankRun {
  id: number;
  bank_id: number;
  bank_name: string;
  collection_id: string;
  status: 'running' | 'done' | 'failed';
  done: number;
  total: number;
  created_at: string;
  finished_at: string | null;
  items: ReportItem[];
}

export interface NoteCreate {
  collection_id: string;
  question: string;
  answer_md: string;
  coverage: Coverage;
  citations: Citation[];
  comment?: string | null;
}

export interface Note extends NoteCreate {
  id: number;
  created_at: string;
}

// Collection-wide synthesis (home page)
export type InsightKind = 'theme' | 'contradiction' | 'trend' | 'gap';

export interface InsightCitation {
  source_id: number;
  source_title: string;
  source_type: SourceType;
  published_at: string | null;
  app_link: string;
}

export interface Insight {
  kind: InsightKind;
  title: string;
  detail: string;
  tag: string | null;
  sources: InsightCitation[];
}

export interface CoverageTopic {
  tag: string;
  sources: number;
  gap: boolean;
}

export interface TimelineBucket {
  period: string;
  sources: number;
}

export interface CollectionAnalysis {
  collection_id: string;
  status: 'ready' | 'running' | 'failed' | 'empty';
  model: string | null;
  source_count: number;
  segment_count: number;
  consensus: number | null;
  insights: Insight[];
  coverage: CoverageTopic[];
  timeline: TimelineBucket[];
  stale: boolean;
  error: string | null;
  generated_at: string | null;
}
