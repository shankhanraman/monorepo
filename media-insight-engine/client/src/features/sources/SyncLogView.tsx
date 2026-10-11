import type { SyncAction, SyncLog } from '../../types';
import { formatDateTime } from '../../lib/format';

const ICONS: Record<SyncAction, string> = { queued: '⏳', skipped: '✓', failed: '✗', archived: '🗄' };

export function SyncLogView({ log }: { log: SyncLog }) {
  const { summary } = log;
  return (
    <section className="card sync-log" aria-labelledby="sync-log-title">
      <h3 id="sync-log-title">Last sync · {formatDateTime(log.created_at)}</h3>
      <p className="meta">
        {summary.queued} queued · {summary.skipped} skipped · {summary.failed} failed · {summary.archived} archived
      </p>
      <ul className="list-reset">
        {log.entries.map((e, i) => (
          <li key={`${e.url}-${i}`} className={`sync-entry sync-${e.action}`}>
            <span className="sync-icon" aria-hidden="true">
              {ICONS[e.action]}
            </span>
            <span className="visually-hidden">{e.action}:</span>
            <span className="sync-text">
              <span className="sync-label">{e.label || e.url}</span>
              {e.label && <span className="sync-url">{e.url}</span>}
              <span className="sync-reason">{e.reason}</span>
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
