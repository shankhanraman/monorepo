import { useCallback, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { bankRunReportUrl, getBankRun } from '../../api';
import { AnswerText } from '../../lib/AnswerText';
import { CoverageBadge } from '../../lib/CoverageBadge';
import { errorMessage, formatDateTime, publishedLabel } from '../../lib/format';
import { usePolling } from '../../lib/usePolling';
import type { BankRun, ReportItem } from '../../types';
import { useCollection } from '../collections/CollectionLayout';
import './question-bank.css';

export function BankReportPage() {
  const collection = useCollection();
  const { runId: runParam } = useParams();
  const runId = Number(runParam);
  const [run, setRun] = useState<BankRun | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setRun(await getBankRun(runId));
      setError(null);
    } catch (e) {
      setError(errorMessage(e));
    }
  }, [runId]);
  useEffect(() => {
    void load();
  }, [load]);
  usePolling(load, 2000, run?.status === 'running');

  const back = (
    <p className="no-print">
      <Link to={`/c/${encodeURIComponent(collection.id)}/banks`}>← Question banks</Link>
    </p>
  );
  if (!run) {
    return (
      <div>
        {back}
        {error ? (
          <div className="banner error-banner" role="alert">
            Could not load the report: {error}
          </div>
        ) : (
          <p className="muted">Loading report…</p>
        )}
      </div>
    );
  }

  const running = run.status === 'running';
  return (
    <div className="report">
      {back}
      <h2>{run.bank_name}</h2>
      <p className="meta">
        {collection.name} · run {run.id} · started {formatDateTime(run.created_at)}
        {run.finished_at && ` · finished ${formatDateTime(run.finished_at)}`}
      </p>
      <p className="meta">Summary of sources. Verify on the official admissions site.</p>

      <div className="progress-row" role="status">
        <progress value={run.done} max={Math.max(run.total, 1)} aria-label="Questions answered" />
        <span>
          {run.done} / {run.total} questions · {running ? 'running…' : run.status}
        </span>
      </div>
      {error && (
        <div className="banner error-banner no-print" role="alert">
          Refresh failed: {error}
        </div>
      )}

      <div className="row report-actions no-print">
        {running ? (
          <span className="muted">Export Markdown is available when the run finishes.</span>
        ) : (
          <a className="button" href={bankRunReportUrl(run.id)}>
            Export Markdown
          </a>
        )}
        <button type="button" onClick={() => window.print()}>
          Print / PDF
        </button>
      </div>

      <ol className="list-reset report-items">
        {run.items.map((item) => (
          <ReportItemView key={item.index} item={item} idPrefix={`run-${run.id}-q${item.index}`} />
        ))}
      </ol>
    </div>
  );
}

function ReportItemView({ item, idPrefix }: { item: ReportItem; idPrefix: string }) {
  const [activeN, setActiveN] = useState<number | null>(null);
  const watchId = (n: number) => `${idPrefix}-watch-${n}`;
  const showWatch = (n: number) => {
    setActiveN(n);
    const el = document.getElementById(watchId(n));
    el?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    el?.focus({ preventScroll: true });
  };

  return (
    <li className="card report-item">
      <h3>
        {item.index + 1}. {item.question}
      </h3>
      {item.status === 'pending' && <p className="muted">Waiting for an answer…</p>}
      {item.status === 'failed' && <p className="error">Failed: {item.error ?? 'unknown error'}</p>}
      {item.status === 'done' && (
        <>
          <CoverageBadge coverage={item.coverage} />
          {item.stale_warning && <p className="banner warning">⚠ {item.stale_warning}</p>}
          <AnswerText text={item.answer_md ?? ''} known={item.watch.map((w) => w.n)} onCite={showWatch} />
          {item.watch.length > 0 && (
            <>
              <h4>Watch these</h4>
              <ol className="list-reset watch-list">
                {item.watch.map((w) => (
                  <li key={w.n} id={watchId(w.n)} tabIndex={-1} className={activeN === w.n ? 'is-active' : undefined}>
                    <span className="cite-n">[{w.n}]</span>{' '}
                    <a href={w.deep_link} target="_blank" rel="noopener noreferrer">
                      {w.label} · {w.source_title}
                    </a>{' '}
                    <span className="meta">
                      ({publishedLabel(w.published_at)}){w.stale && ' ⚠'}
                    </span>{' '}
                    <Link className="no-print" to={w.app_link}>
                      Play here
                    </Link>
                  </li>
                ))}
              </ol>
            </>
          )}
        </>
      )}
    </li>
  );
}
