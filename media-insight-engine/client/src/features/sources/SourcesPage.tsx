import { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { ApiError, getLatestSyncLog, listSources, syncCollection } from '../../api';
import { errorMessage, publishedLabel, sourceTitle } from '../../lib/format';
import { progressPercent } from '../../lib/sourceLabels';
import { StaleBadge } from '../../lib/StaleBadge';
import { formatTime } from '../../lib/time';
import { usePolling } from '../../lib/usePolling';
import type { SourceSummary, SyncLog } from '../../types';
import { useCollection, useReloadCollections } from '../collections/CollectionLayout';
import { IN_PROGRESS, StatusBadge } from './StatusBadge';
import { SyncLogView } from './SyncLogView';
import './sources.css';

/** After a 409 the Sync button stays disabled this long before the user may retry. */
const SYNC_RETRY_MS = 10_000;

export function SourcesPage() {
  const collection = useCollection();
  const reloadCollections = useReloadCollections();
  const cid = collection.id;
  const [sources, setSources] = useState<SourceSummary[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [syncLog, setSyncLog] = useState<SyncLog | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [syncBlocked, setSyncBlocked] = useState(false);
  const [syncError, setSyncError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setSources(await listSources(cid));
      setLoadError(null);
    } catch (e) {
      setLoadError(errorMessage(e));
    }
  }, [cid]);

  useEffect(() => {
    void refresh();
    getLatestSyncLog(cid).then(setSyncLog, (e: unknown) => {
      // 404 = never synced: show nothing
      if (!(e instanceof ApiError && e.status === 404)) setSyncError(errorMessage(e));
    });
  }, [cid, refresh]);

  const inProgress = sources?.some((s) => IN_PROGRESS.has(s.status)) ?? false;
  usePolling(refresh, 3000, inProgress);

  // Ingest finished: refresh the college list so `source_counts` are current.
  const wasInProgress = useRef(inProgress);
  useEffect(() => {
    if (wasInProgress.current && !inProgress) void reloadCollections();
    wasInProgress.current = inProgress;
  }, [inProgress, reloadCollections]);

  const sync = async () => {
    setSyncing(true);
    setSyncError(null);
    try {
      setSyncLog(await syncCollection(cid));
      void reloadCollections(); // the sync may have changed lens_tags, focus_note and source_counts
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        setSyncError('A sync for this college is already running. Try again in a moment.');
        setSyncBlocked(true);
        window.setTimeout(() => setSyncBlocked(false), SYNC_RETRY_MS);
      } else {
        setSyncError(errorMessage(e)); // 422: broken YAML (detail), 404: no config file
      }
    } finally {
      setSyncing(false);
    }
    await refresh(); // picks up queued sources, which starts polling
  };

  return (
    <div>
      <div className="row sources-head">
        <h2>{collection.name} sources</h2>
        <button type="button" className="primary" onClick={sync} disabled={syncing || syncBlocked}>
          {syncing ? 'Syncing…' : 'Sync'}
        </button>
      </div>
      {collection.focus_note && <p className="meta">Focus: {collection.focus_note}</p>}
      {syncError && (
        <div className="banner error-banner" role="alert">
          {syncError}
        </div>
      )}
      {syncLog && <SyncLogView log={syncLog} />}

      {loadError && (
        <div className="banner error-banner" role="alert">
          Could not load sources: {loadError}
        </div>
      )}
      {inProgress && (
        <p className="meta" role="status">
          Ingest in progress. This list refreshes every 3 seconds.
        </p>
      )}
      {sources === null && !loadError && <p className="muted">Loading sources…</p>}
      {sources?.length === 0 && <p className="muted">No sources yet. Press Sync to read this college's config file.</p>}
      {sources && sources.length > 0 && (
        <ul className="list-reset">
          {sources.map((s) => (
            <SourceRow key={s.id} source={s} />
          ))}
        </ul>
      )}
    </div>
  );
}

function SourceRow({ source: s }: { source: SourceSummary }) {
  const rest: string[] = [];
  if (s.duration_s != null) rest.push(formatTime(s.duration_s));
  if (s.status === 'ready') rest.push(`${s.segment_count} segments`);
  if (s.feed_url) rest.push('from feed');
  const progress = s.status === 'transcribing' ? progressPercent(s.progress) : null;
  return (
    <li className="card source-row">
      <div className="row">
        <StatusBadge status={s.status} progress={s.progress} />
        <span className={`badge type-badge type-${s.type}`}>{TYPE_LABELS[s.type] ?? s.type}</span>
        {s.priority === 'high' && <span className="badge">high priority</span>}
      </div>
      {progress !== null && (
        <progress className="slim-progress" value={progress} max={100} aria-label="Transcription progress" />
      )}
      <h3 className="source-title">
        <Link to={`/sources/${s.id}`}>{sourceTitle(s)}</Link>
      </h3>
      <p className="meta">
        {s.host && `${s.host} · `}
        {publishedLabel(s.published_at)}
        {s.stale && (
          <>
            {' '}
            <StaleBadge />
          </>
        )}
        {rest.length > 0 && ` · ${rest.join(' · ')}`}
      </p>
      {s.status === 'failed' && s.error && <p className="error">Error: {s.error}</p>}
    </li>
  );
}

const TYPE_LABELS: Record<SourceSummary['type'], string> = { youtube: 'youtube', web: 'web', audio: 'audio', pdf: 'PDF' };
