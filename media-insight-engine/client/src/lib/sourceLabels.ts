import type { SourceStatus, SourceType } from '../types';

/** YouTube and audio sources are time-based (seconds, a player); web and PDF are section-based. */
export const isTimeBased = (type: SourceType): boolean => type === 'youtube' || type === 'audio';

const OPEN_TEXT: Record<SourceType, string> = {
  youtube: 'Open on YouTube',
  audio: 'Open audio',
  web: 'Open page',
  pdf: 'Open PDF page',
};

/** Text of a citation's external `deep_link`. */
export const openLinkText = (type: SourceType): string => OPEN_TEXT[type] ?? 'Open';

/** Text of a citation's in-app `app_link`: plays for youtube/audio, scrolls to the section for web/pdf. */
export const appLinkText = (type: SourceType): string => (isTimeBased(type) ? 'Play here' : 'Show here');

/** Page number from a PDF deep link (`…pdf#page=3`), or null. */
export function pdfPage(deepLink: string): number | null {
  const m = /#(?:.*&)?page=(\d+)/.exec(deepLink);
  return m ? Number(m[1]) : null;
}

/** "Open page 3" for a PDF deep link with a page, otherwise "Open in PDF". */
export function pdfLinkText(deepLink: string): string {
  const page = pdfPage(deepLink);
  return page === null ? 'Open in PDF' : `Open page ${page}`;
}

/** `progress` as a whole percentage (0–100), or null when there is none. */
export function progressPercent(progress: number | null | undefined): number | null {
  if (progress == null || !Number.isFinite(progress)) return null;
  return Math.min(100, Math.max(0, Math.round(progress)));
}

/** Status badge text: "transcribing 42 %" while transcribing with a known progress, otherwise the status. */
export function statusLabel(status: SourceStatus, progress: number | null | undefined): string {
  const pct = status === 'transcribing' ? progressPercent(progress) : null;
  return pct === null ? status : `${status} ${pct} %`;
}

/** Tooltip of the "may be outdated" badge. */
export const STALE_TITLE = 'Older than 18 months or date unknown: verify on the official site';
