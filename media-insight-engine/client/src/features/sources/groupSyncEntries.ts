import type { SyncEntry } from '../../types';

export interface SyncLine {
  entry: SyncEntry;
  /** For a `feed` line: the episode lines that came from this feed (their `feed_url` equals its `url`). */
  episodes: SyncEntry[];
}

/**
 * Nests episode entries under the feed line they came from, keeping the server's order.
 * An episode whose feed line has not appeared before it stays a top-level line.
 */
export function groupSyncEntries(entries: readonly SyncEntry[]): SyncLine[] {
  const lines: SyncLine[] = [];
  const feeds = new Map<string, SyncLine>();
  for (const entry of entries) {
    const feed = entry.action !== 'feed' && entry.feed_url ? feeds.get(entry.feed_url) : undefined;
    if (feed) {
      feed.episodes.push(entry);
      continue;
    }
    const line: SyncLine = { entry, episodes: [] };
    if (entry.action === 'feed') feeds.set(entry.url, line);
    lines.push(line);
  }
  return lines;
}
