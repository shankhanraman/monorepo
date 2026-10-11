import { statusLabel } from '../../lib/sourceLabels';
import type { SourceStatus } from '../../types';
import './sources.css';

export const IN_PROGRESS: ReadonlySet<SourceStatus> = new Set(['queued', 'transcribing', 'analyzing']);

/** Status pill. Pass `progress` to show "transcribing 42 %" while transcribing. */
export function StatusBadge({ status, progress = null }: { status: SourceStatus; progress?: number | null }) {
  return (
    <span className={`badge status-${status}`}>
      {IN_PROGRESS.has(status) && <span className="status-dot" aria-hidden="true" />}
      {statusLabel(status, progress)}
    </span>
  );
}
