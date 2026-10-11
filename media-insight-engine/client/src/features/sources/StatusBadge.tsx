import type { SourceStatus } from '../../types';

export const IN_PROGRESS: ReadonlySet<SourceStatus> = new Set(['queued', 'transcribing', 'analyzing']);

export function StatusBadge({ status }: { status: SourceStatus }) {
  return (
    <span className={`badge status-${status}`}>
      {IN_PROGRESS.has(status) && <span className="status-dot" aria-hidden="true" />}
      {status}
    </span>
  );
}
