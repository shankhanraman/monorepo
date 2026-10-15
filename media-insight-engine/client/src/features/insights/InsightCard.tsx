import { Link } from 'react-router-dom';
import type { Insight, InsightKind } from '../../types';
import { formatTime } from '../../lib/time';

const KIND: Record<InsightKind, { label: string; cls: string }> = {
  theme: { label: 'Theme · Agreement', cls: 'theme' },
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

interface Props {
  insight: Insight;
  top?: boolean;
  /** Filter the whole board to this tag (the tag pill is a button when provided). */
  onFilterTag?: (tag: string) => void;
}

/** One insight in the Findings masonry: category, headline, synthesis, and its supporting sources. */
export function InsightCard({ insight, top = false, onFilterTag }: Props) {
  const k = KIND[insight.kind];
  return (
    <article className={`ins-card ${k.cls}${top ? ' is-top' : ''}`}>
      {top && <div className="ins-start">Start here</div>}
      <div className={`ins-cat ${k.cls}`}>
        <i className="ins-dot" />
        {k.label}
        {insight.tag &&
          (onFilterTag ? (
            <button
              type="button"
              className="ins-tag ins-tag-btn"
              onClick={() => onFilterTag(insight.tag as string)}
              title={`Filter findings by “${insight.tag}”`}
            >
              {insight.tag}
            </button>
          ) : (
            <span className="ins-tag">{insight.tag}</span>
          ))}
      </div>
      <h3 className="ins-card-title">{insight.title}</h3>
      <p className="ins-card-detail">{insight.detail}</p>
      <div className={`ins-confidence ${insight.confidence ?? 'medium'}`}>
        {insight.confidence ?? 'medium'} confidence
        {insight.evidence && insight.evidence.length > 0 && ` · ${insight.evidence.length} evidence excerpts`}
      </div>
      {insight.recommended_action && (
        <div className="ins-action-note">
          <span>Next action</span>
          <p>{insight.recommended_action}</p>
        </div>
      )}
      {insight.evidence && insight.evidence.length > 0 && (
        <details className="ins-evidence">
          <summary>Why this finding was made</summary>
          <div className="ins-evidence-list">
            {insight.evidence.map((e, n) => (
              <blockquote key={`${e.source_id}:${n}`} className={e.role === 'opposes' ? 'opposes' : ''}>
                <p>“{e.quote}”</p>
                <Link to={e.app_link}>
                  {e.source_title}{e.timestamp_s > 0 ? ` · ${formatTime(e.timestamp_s)}` : ''} · {e.role}
                </Link>
              </blockquote>
            ))}
          </div>
        </details>
      )}
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
