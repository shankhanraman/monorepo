import { STALE_TITLE } from './sourceLabels';

/** "may be outdated" badge for sources with `stale: true`. Shown next to the date. */
export function StaleBadge() {
  return (
    <span className="badge stale-badge" title={STALE_TITLE}>
      may be outdated<span className="visually-hidden">: {STALE_TITLE}</span>
    </span>
  );
}
