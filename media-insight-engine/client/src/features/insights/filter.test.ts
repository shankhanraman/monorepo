import { describe, expect, it } from 'vitest';
import type { Insight } from '../../types';
import { insightMatchesFilter } from './InsightsPage';

const card = (kind: Insight['kind'], tag: string | null): Insight => ({
  kind,
  title: 't',
  detail: 'd',
  tag,
  sources: [],
});

describe('insightMatchesFilter', () => {
  it('passes everything when there is no filter', () => {
    expect(insightMatchesFilter(card('theme', 'essays'), null)).toBe(true);
    expect(insightMatchesFilter(card('gap', null), null)).toBe(true);
  });

  it('filters by kind', () => {
    const f = { type: 'kind', value: 'contradiction' } as const;
    expect(insightMatchesFilter(card('contradiction', 'testing'), f)).toBe(true);
    expect(insightMatchesFilter(card('theme', 'testing'), f)).toBe(false);
  });

  it('filters by tag (exact match, tolerates null tags)', () => {
    const f = { type: 'tag', value: 'essays' } as const;
    expect(insightMatchesFilter(card('theme', 'essays'), f)).toBe(true);
    expect(insightMatchesFilter(card('trend', 'academics'), f)).toBe(false);
    expect(insightMatchesFilter(card('gap', null), f)).toBe(false);
  });

  it('timeline click (kind=trend) surfaces only trend cards', () => {
    const f = { type: 'kind', value: 'trend' } as const;
    expect(insightMatchesFilter(card('trend', null), f)).toBe(true);
    expect(insightMatchesFilter(card('gap', null), f)).toBe(false);
  });
});
