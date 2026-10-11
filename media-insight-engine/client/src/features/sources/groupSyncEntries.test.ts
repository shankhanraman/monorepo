import { describe, expect, it } from 'vitest';
import type { SyncAction, SyncEntry } from '../../types';
import { groupSyncEntries } from './groupSyncEntries';

const FEED = 'https://feeds.example.com/show';
const e = (url: string, action: SyncAction, feed_url: string | null = null): SyncEntry => ({
  url,
  label: null,
  action,
  reason: '',
  source_id: null,
  feed_url,
});

describe('groupSyncEntries', () => {
  it('nests episodes under their feed line, in order', () => {
    const lines = groupSyncEntries([
      e('https://youtu.be/a', 'skipped'),
      e(FEED, 'feed'),
      e('https://cdn.example.com/42.mp3', 'queued', FEED),
      e('https://cdn.example.com/41.mp3', 'skipped', FEED),
      e('https://youtu.be/old', 'archived'),
    ]);
    expect(lines.map((l) => l.entry.url)).toEqual(['https://youtu.be/a', FEED, 'https://youtu.be/old']);
    expect(lines[1].episodes.map((x) => x.url)).toEqual([
      'https://cdn.example.com/42.mp3',
      'https://cdn.example.com/41.mp3',
    ]);
    expect(lines[0].episodes).toEqual([]);
  });

  it('keeps two feeds apart', () => {
    const other = 'https://feeds.example.com/other';
    const lines = groupSyncEntries([
      e(FEED, 'feed'),
      e('https://cdn.example.com/1.mp3', 'queued', FEED),
      e(other, 'feed'),
      e('https://cdn.example.com/2.mp3', 'queued', other),
    ]);
    expect(lines).toHaveLength(2);
    expect(lines[0].episodes.map((x) => x.url)).toEqual(['https://cdn.example.com/1.mp3']);
    expect(lines[1].episodes.map((x) => x.url)).toEqual(['https://cdn.example.com/2.mp3']);
  });

  it('leaves an episode without a preceding feed line at the top level', () => {
    const lines = groupSyncEntries([e('https://cdn.example.com/1.mp3', 'queued', FEED)]);
    expect(lines).toHaveLength(1);
    expect(lines[0].episodes).toEqual([]);
  });

  it('returns an empty list for no entries', () => {
    expect(groupSyncEntries([])).toEqual([]);
  });
});
