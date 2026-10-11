import type { SyncAction, SyncEntry, SyncLog } from '../../types';
import { formatDateTime } from '../../lib/format';
import { groupSyncEntries } from './groupSyncEntries';

const ICONS: Record<SyncAction, string> = { queued: '⏳', skipped: '✓', failed: '✗', archived: '🗄', feed: '📻' };

export function SyncLogView({ log }: { log: SyncLog }) {
  const { summary } = log;
  return (
    <section className="card sync-log" aria-labelledby="sync-log-title">
      <h3 id="sync-log-title">Last sync · {formatDateTime(log.created_at)}</h3>
      <p className="meta">
        {summary.queued} queued · {summary.skipped} skipped · {summary.failed} failed · {summary.archived} archived
      </p>
      <ul className="list-reset">
        {groupSyncEntries(log.entries).map(({ entry, episodes }, i) => (
          <li key={`${entry.url}-${i}`} className={`sync-line sync-${entry.action}`}>
            <EntryRow entry={entry} />
            {episodes.length > 0 && (
              <ul className="list-reset sync-episodes" aria-label={`Episodes from ${entry.label || entry.url}`}>
                {episodes.map((ep, j) => (
                  <li key={`${ep.url}-${j}`} className={`sync-line sync-${ep.action}`}>
                    <EntryRow entry={ep} />
                  </li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

function EntryRow({ entry: e }: { entry: SyncEntry }) {
  return (
    <div className="sync-entry">
      <span className="sync-icon" aria-hidden="true">
        {ICONS[e.action] ?? '•'}
      </span>
      <span className="visually-hidden">{e.action}:</span>
      <span className="sync-text">
        <span className="sync-label">{e.label || e.url}</span>
        {e.label && <span className="sync-url">{e.url}</span>}
        <span className="sync-reason">{e.reason}</span>
      </span>
    </div>
  );
}
