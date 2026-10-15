import type { CollectionAnalysis, InsightKind } from '../../types';
import type { InsightFilter } from './InsightsPage';

interface Props {
  analysis: CollectionAnalysis;
  filter: InsightFilter;
  onFilter: (f: InsightFilter) => void;
}

/** The quantitative half — and a navigation surface: every row, bar and column filters the
 *  Findings on the left (an action-items hero, per-tag coverage bars, a source timeline). */
export function Atlas({ analysis, filter, onFilter }: Props) {
  const { source_count, segment_count, coverage, timeline } = analysis;
  const themes = analysis.insights.filter((i) => i.kind === 'theme').length;
  const conflicts = analysis.insights.filter((i) => i.kind === 'contradiction').length;
  const gaps = coverage.filter((c) => c.gap).length;
  const evidenceCount = analysis.insights.reduce((n, i) => n + (i.evidence?.length ?? 0), 0);
  const highConfidence = analysis.insights.filter((i) => i.confidence === 'high').length;
  const total = Math.max(1, source_count); // coverage is "of N sources", not "of the biggest tag"
  const maxTl = Math.max(1, ...timeline.map((t) => t.sources));

  const kindActive = (k: InsightKind) => filter?.type === 'kind' && filter.value === k;
  const tagActive = (t: string) => filter?.type === 'tag' && filter.value === t;
  const toggleKind = (k: InsightKind) => onFilter(kindActive(k) ? null : { type: 'kind', value: k });
  const toggleTag = (t: string) => onFilter(tagActive(t) ? null : { type: 'tag', value: t });

  // Lead with what a counselor should act on, most urgent first — each row filters the Findings.
  const actions: { n: number; cls: string; kind: InsightKind; label: string }[] = [
    { n: conflicts, cls: 'warn', kind: 'contradiction', label: conflicts === 1 ? 'conflict to resolve' : 'conflicts to resolve' },
    { n: gaps, cls: 'gap', kind: 'gap', label: gaps === 1 ? 'topic barely covered' : 'topics barely covered' },
    { n: themes, cls: 'agree', kind: 'theme', label: themes === 1 ? 'point of consensus' : 'points of consensus' },
  ];

  return (
    <div className="ins-atlas">
      <div className="ins-atlas-head">
        <div className="ins-atlas-k">The Atlas · collection at a glance</div>
        <h2 className="ins-atlas-title">What to look at</h2>
      </div>
      <div className="ins-atlas-body">
        <div className="ins-hero">
          <ul className="ins-action-list">
            {actions.map((a) => (
              <li key={a.kind}>
                <button
                  type="button"
                  className={`ins-action ${a.cls}${a.n === 0 ? ' zero' : ''}${kindActive(a.kind) ? ' is-active' : ''}`}
                  onClick={() => toggleKind(a.kind)}
                  disabled={a.n === 0}
                  aria-pressed={kindActive(a.kind)}
                >
                  <b>{a.n}</b>
                  <span>{a.label}</span>
                </button>
              </li>
            ))}
          </ul>
          <p className="ins-totals">
            {source_count} source{source_count === 1 ? '' : 's'} · {segment_count} segment
            {segment_count === 1 ? '' : 's'} analyzed
          </p>
          <div className="ins-quality-grid" aria-label="Evidence quality">
            <span><b>{evidenceCount}</b> verified excerpts</span>
            <span><b>{highConfidence}</b> high-confidence findings</span>
          </div>
          {source_count < 3 && (
            <p className="ins-small-sample">Small collection: treat agreement and trend findings as provisional.</p>
          )}
        </div>

        {coverage.length > 0 && (
          <>
            <p className="ins-sec-title">Topic coverage — click a tag to filter</p>
            <div className="ins-bars">
              {coverage.map((c) => (
                <button
                  type="button"
                  key={c.tag}
                  className={`ins-bar${c.gap ? ' gap' : ''}${tagActive(c.tag) ? ' is-active' : ''}`}
                  onClick={() => toggleTag(c.tag)}
                  aria-pressed={tagActive(c.tag)}
                  aria-label={`${c.tag}: ${c.sources} of ${source_count} sources${c.gap ? ' — coverage gap' : ''}. Filter findings.`}
                >
                  <span className="ins-lab" title={c.tag}>
                    {c.tag}
                    {c.gap && <span className="ins-tag gapt">gap</span>}
                  </span>
                  <span className="ins-track">
                    <span className="ins-fill" style={{ width: `${(c.sources / total) * 100}%` }} />
                  </span>
                  <span className="ins-cnt">
                    {c.sources}/{source_count}
                  </span>
                </button>
              ))}
            </div>
          </>
        )}

        {timeline.length > 0 && (
          <div className="ins-timeline">
            <p className="ins-sec-title">Sources over time — click to see trends</p>
            <div className="ins-tl">
              {timeline.map((t) => (
                <button
                  type="button"
                  key={t.period}
                  className={`ins-tl-col${kindActive('trend') ? ' is-active' : ''}`}
                  onClick={() => toggleKind('trend')}
                  aria-pressed={kindActive('trend')}
                  aria-label={`${t.period}: ${t.sources} source${t.sources === 1 ? '' : 's'}. Filter findings to trends.`}
                >
                  <span className="ins-tl-bar" style={{ height: `${(t.sources / maxTl) * 100}%` }} />
                  <span className="ins-tl-cnt">{t.sources}</span>
                  <span className="ins-tl-yr">{t.period}</span>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
