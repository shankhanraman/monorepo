import { describe, expect, it } from 'vitest';
import { appLinkText, isTimeBased, openLinkText, pdfLinkText, pdfPage, progressPercent, statusLabel } from './sourceLabels';

describe('link texts', () => {
  it('names the external link by source type', () => {
    expect(openLinkText('youtube')).toBe('Open on YouTube');
    expect(openLinkText('audio')).toBe('Open audio');
    expect(openLinkText('web')).toBe('Open page');
    expect(openLinkText('pdf')).toBe('Open PDF page');
  });
  it('plays time-based sources and shows section-based ones', () => {
    expect(appLinkText('youtube')).toBe('Play here');
    expect(appLinkText('audio')).toBe('Play here');
    expect(appLinkText('web')).toBe('Show here');
    expect(appLinkText('pdf')).toBe('Show here');
    expect(isTimeBased('audio')).toBe(true);
    expect(isTimeBased('pdf')).toBe(false);
  });
  it('falls back to "Open" for an unknown type', () => {
    expect(openLinkText('video' as never)).toBe('Open');
  });
});

describe('pdf links', () => {
  it('reads the page from #page=N', () => {
    expect(pdfPage('https://x.edu/guide.pdf#page=3')).toBe(3);
    expect(pdfPage('https://x.edu/guide.pdf#zoom=100&page=12')).toBe(12);
    expect(pdfLinkText('https://x.edu/guide.pdf#page=3')).toBe('Open page 3');
  });
  it('falls back to "Open in PDF" without a page', () => {
    expect(pdfPage('https://x.edu/guide.pdf')).toBeNull();
    expect(pdfPage('https://x.edu/guide.pdf?page=3')).toBeNull();
    expect(pdfLinkText('https://x.edu/guide.pdf')).toBe('Open in PDF');
  });
});

describe('status label', () => {
  it('adds the percentage while transcribing', () => {
    expect(statusLabel('transcribing', 42)).toBe('transcribing 42 %');
    expect(statusLabel('transcribing', 0)).toBe('transcribing 0 %');
  });
  it('is the plain status otherwise', () => {
    expect(statusLabel('transcribing', null)).toBe('transcribing');
    expect(statusLabel('queued', 42)).toBe('queued');
    expect(statusLabel('failed', null)).toBe('failed');
  });
  it('rounds and clamps progress', () => {
    expect(progressPercent(41.6)).toBe(42);
    expect(progressPercent(140)).toBe(100);
    expect(progressPercent(-5)).toBe(0);
    expect(progressPercent(Number.NaN)).toBeNull();
    expect(progressPercent(undefined)).toBeNull();
  });
});
