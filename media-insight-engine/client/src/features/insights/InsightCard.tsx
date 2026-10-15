import { Link } from 'react-router-dom';
import type { Insight, InsightKind } from '../../types';

const KIND: Record<InsightKind, { label: string; cls: string }> = {
  theme: { label: 'Theme · Consensus', cls: 'theme' },
  contradiction: { label: 'Contradiction', cls: 'contra' },
  trend: { label: 'Trend', cls: 'trend' },
  gap: { label: 'Coverage gap', cls: 'gap' },
};

function countLabel(i: Insight): string {
  const n = i.sources.length;
  if (i.kind === 'theme') return `${n} agree`;
  if (i.kind === 'contradiction') return `${n} conflict`;
  if (i.kind === 'gap') return n ? `${n} of your sources` : 'not in your sources';
  return `${n} source${n === 1 ? '' : 's'}`;
}

/** One insight in the Findings masonry: category, headline, synthesis, and its supporting sources. */
export function InsightCard({ insight, top = false }: { insight: Insight; top?: boolean }) {
  const k = KIND[insight.kind];
  return (
    <article className={`ins-card ${k.cls}${top ? ' is-top' : ''}`}>
      {top && <div className="ins-start">Start here</div>}
      <div className={`ins-cat ${k.cls}`}>
        <i className="ins-dot" />
        {k.label}
        {insight.tag && <span className="ins-tag">{insight.tag}</span>}
      </div>
      <h3 className="ins-card-title">{insight.title}</h3>
      <p className="ins-card-detail">{insight.detail}</p>
      <div className="ins-cites">
        <span className="ins-n">{countLabel(insight)}</span>
        {insight.sources.map((s) => (
          <Link key={s.source_id} className="ins-chip" to={s.app_link} title={s.source_title}>
            {s.source_title}
          </Link>
        ))}
      </div>
    </article>
  );
}
