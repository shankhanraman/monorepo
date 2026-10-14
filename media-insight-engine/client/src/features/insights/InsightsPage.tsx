import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { getCollectionInsights, refreshCollectionInsights } from '../../api';
import { errorMessage } from '../../lib/format';
import { usePolling } from '../../lib/usePolling';
import type { CollectionAnalysis, InsightKind } from '../../types';
import { useCollection, useReloadCollections } from '../collections/CollectionLayout';
import { Atlas } from './Atlas';
import { InsightCard } from './InsightCard';
import './insights.css';

const LEGEND: { kind: InsightKind; label: string; cls: string }[] = [
  { kind: 'theme', label: 'Theme', cls: 'theme' },
  { kind: 'contradiction', label: 'Conflict', cls: 'contra' },
  { kind: 'trend', label: 'Trend', cls: 'trend' },
  { kind: 'gap', label: 'Gap', cls: 'gap' },
];

export function InsightsPage() {
  const collection = useCollection();
  const reloadCollections = useReloadCollections();
  const cid = collection.id;
  const [analysis, setAnalysis] = useState<CollectionAnalysis | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [rerunning, setRerunning] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setAnalysis(await getCollectionInsights(cid));
      setLoadError(null);
    } catch (e) {
      setLoadError(errorMessage(e));
    }
    // Keep source_counts fresh so polling can actually stop once ingest drains (the collection
    // prop is otherwise a one-time snapshot that never updates on this page).
    void reloadCollections();
  }, [cid, reloadCollections]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // Poll while a run is in flight, while sources are still ingesting (insights follow the drain),
  // or while a non-failed result is stale (a synthesis is queued to replace it).
  const polling =
    analysis?.status === 'running' ||
    collection.source_counts.in_progress > 0 ||
    (analysis?.stale === true && analysis.status !== 'failed');
  usePolling(refresh, 3000, polling);

  const rerun = useCallback(async () => {
    setRerunning(true);
    // Optimistically show "running" so the badge animates and polling kicks in; the background
    // synthesis updates the real status, which the next poll picks up.
    setAnalysis((a) => (a ? { ...a, status: 'running', error: null } : a));
    try {
      await refreshCollectionInsights(cid);
    } catch (e) {
      setLoadError(errorMessage(e));
      void refresh(); // trigger failed to enqueue — revert the optimistic status to real state
    } finally {
      setRerunning(false);
    }
  }, [cid, refresh]);

  if (loadError && !analysis) {
    return (
      <div>
        <h2>{collection.name} insights</h2>
        <div className="banner error-banner" role="alert">
          Could not load insights: {loadError}
        </div>
      </div>
    );
  }
  if (!analysis) return <p className="muted">Loading insights…</p>;

  const hasData = analysis.insights.length > 0 || analysis.coverage.length > 0;
  if (analysis.status === 'empty' && !hasData) {
    return (
      <div>
        <h2>{collection.name} insights</h2>
        <p className="muted">
          No insights yet. <Link to={`/c/${encodeURIComponent(cid)}/sources`}>Sync this college's sources</Link> and the
          analytical agent will read them together and surface themes, contradictions, trends and gaps here.
        </p>
      </div>
    );
  }

  return (
    <div className="ins-page">
      <header className="ins-masthead">
        <div>
          <div className="ins-kicker">{collection.name} · Collection insights</div>
          <h2 className="ins-h1">Insights</h2>
          <p className="ins-sub">
            What the analytical agent found by reading all {analysis.source_count} sources together — on the left the
            findings, on the right the map.
          </p>
        </div>
        <div className="ins-actions">
          <StatusBadge analysis={analysis} />
          {analysis.status !== 'running' && (
            <button type="button" className="ins-rerun" onClick={rerun} disabled={rerunning}>
              {rerunning ? 'Starting…' : 'Re-run analysis'}
            </button>
          )}
        </div>
      </header>

      {analysis.status === 'failed' && (
        <div className="banner error-banner" role="alert">
          The last analysis failed{analysis.error ? `: ${analysis.error}` : ''}. The Atlas below is still
          current — re-run when the model is available.
        </div>
      )}

      <div className="ins-split">
        <section className="ins-left">
          <div className="ins-pane-label">
            <span>Findings · {analysis.insights.length}</span>
            <div className="ins-legend">
              {LEGEND.map((l) => (
                <span key={l.kind}>
                  <i className={`ins-dot ${l.cls}`} />
                  {l.label}
                </span>
              ))}
            </div>
          </div>
          {analysis.insights.length === 0 ? (
            <p className="muted">
              {analysis.status === 'running'
                ? 'The agent is reading the sources…'
                : analysis.status === 'failed'
                  ? 'The analysis could not run — your sources are indexed and ready. The Atlas on the right is up to date; use “Re-run analysis” to try the agent again.'
                  : 'No cross-cutting insights surfaced yet. Add more sources and re-sync.'}
            </p>
          ) : (
            <div className="ins-grid" aria-live="polite">
              {analysis.insights.map((insight, i) => (
                <InsightCard key={`${insight.kind}:${insight.title}`} insight={insight} top={i === 0} />
              ))}
            </div>
          )}
        </section>

        <aside className="ins-right">
          <Atlas analysis={analysis} />
        </aside>
      </div>
    </div>
  );
}

function Dot() {
  return <span aria-hidden="true">● </span>;
}

function StatusBadge({ analysis }: { analysis: CollectionAnalysis }) {
  if (analysis.status === 'running') {
    return (
      <span className="ins-badge running" role="status">
        <Dot />
        Analyzing…
      </span>
    );
  }
  if (analysis.status === 'failed') {
    return (
      <span className="ins-badge failed">
        <Dot />
        Last refresh failed
      </span>
    );
  }
  if (analysis.stale) {
    return (
      <span className="ins-badge stale" role="status">
        <Dot />
        Updating…
      </span>
    );
  }
  return (
    <span className="ins-badge fresh">
      <Dot />
      Up to date
    </span>
  );
}
