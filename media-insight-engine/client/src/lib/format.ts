import type { SourceSummary } from '../types';

/** Title, falling back to the YAML label, then the URL. */
export const sourceTitle = (s: Pick<SourceSummary, 'title' | 'label' | 'url'>): string => s.title || s.label || s.url;

/** `published_at` as-is, or "date unknown". */
export const publishedLabel = (date: string | null): string => date ?? 'date unknown';

/** ISO date-time → local, human-readable. */
export function formatDateTime(iso: string | null): string {
  if (!iso) return '';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
}

/** Message for any thrown value. */
export const errorMessage = (e: unknown): string => (e instanceof Error ? e.message : String(e));
