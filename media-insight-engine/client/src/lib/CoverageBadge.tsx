import type { Coverage } from '../types';

export function CoverageBadge({ coverage }: { coverage: Coverage | null }) {
  if (!coverage) return null;
  return <span className={`badge coverage-${coverage}`}>Coverage: {coverage}</span>;
}
