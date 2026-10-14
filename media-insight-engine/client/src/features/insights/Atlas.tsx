import type { CollectionAnalysis } from '../../types';

/** The quantitative half: an agreement stat, per-tag coverage bars, and a source timeline. */
export function Atlas({ analysis }: { analysis: CollectionAnalysis }) {
  const { consensus, source_count, segment_count, coverage, timeline } = analysis;
  const themes = analysis.insights.filter((i) => i.kind === 'theme').length;
  const conflicts = analysis.insights.filter((i) => i.kind === 'contradiction').length;
  const gaps = coverage.filter((c) => c.gap).length;
  const total = Math.max(1, source_count); // coverage is "of N sources", not "of the biggest tag"
  const maxTl = Math.max(1, ...timeline.map((t) => t.sources));
  const gaugePct = consensus ?? 0;

  return (
    <div className="ins-atlas">
      <div className="ins-atlas-head">
        <div className="ins-atlas-k">The Atlas · collection at a glance</div>
        <h2 className="ins-atlas-title">Agreement among findings</h2>
      </div>
      <div className="ins-atlas-body">
        <div className="ins-hero">
          <div
            className="ins-gauge"
            style={{ background: `conic-gradient(var(--accent) 0 ${gaugePct}%, var(--surface-2) ${gaugePct}% 100%)` }}
            role="meter"
            aria-valuenow={consensus ?? undefined}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label={`Agreement among findings: ${consensus == null ? 'not enough findings to measure' : `${consensus}%`}`}
          >
            <div className="ins-gauge-val">
              <b>{consensus == null ? '—' : `${consensus}%`}</b>
              <small>Agreement</small>
            </div>
          </div>
          <div className="ins-stats">
            <div className="ins-stat">
              <b>{source_count}</b>
              <span>Sources</span>
            </div>
            <div className="ins-stat">
              <b>{segment_count}</b>
              <span>Segments</span>
            </div>
            <div className="ins-stat warn">
              <b>{conflicts}</b>
              <span>Conflicts</span>
            </div>
            <div className="ins-stat gap">
              <b>{gaps}</b>
              <span>Coverage gaps</span>
            </div>
          </div>
        </div>
        <p className="ins-atlas-note">
          {themes} theme{themes === 1 ? '' : 's'} vs {conflicts} conflict{conflicts === 1 ? '' : 's'} across{' '}
          {source_count} source{source_count === 1 ? '' : 's'}
        </p>

        {coverage.length > 0 && (
          <>
            <p className="ins-sec-title">Topic coverage — sources per Lens tag</p>
            <div className="ins-bars">
              {coverage.map((c) => (
                <div
                  key={c.tag}
                  className={`ins-bar${c.gap ? ' gap' : ''}`}
                  role="img"
                  aria-label={`${c.tag}: ${c.sources} of ${source_count} sources${c.gap ? ' — coverage gap' : ''}`}
                >
                  <div className="ins-lab" title={c.tag}>
                    {c.tag}
                    {c.gap && <span className="ins-tag gapt">gap</span>}
                  </div>
                  <div className="ins-track">
                    <div className="ins-fill" style={{ width: `${(c.sources / total) * 100}%` }} />
                  </div>
                  <div className="ins-cnt">
                    {c.sources}/{source_count}
                  </div>
                </div>
              ))}
            </div>
          </>
        )}

        {timeline.length > 0 && (
          <div className="ins-timeline">
            <p className="ins-sec-title">Sources over time</p>
            <div className="ins-tl">
              {timeline.map((t) => (
                <div
                  key={t.period}
                  className="ins-tl-col"
                  role="img"
                  aria-label={`${t.period}: ${t.sources} source${t.sources === 1 ? '' : 's'}`}
                >
                  <div className="ins-tl-bar" style={{ height: `${(t.sources / maxTl) * 100}%` }} />
                  <div className="ins-tl-cnt">{t.sources}</div>
                  <div className="ins-tl-yr">{t.period}</div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
