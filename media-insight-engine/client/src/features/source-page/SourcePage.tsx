import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useLocation, useParams, useSearchParams } from 'react-router-dom';
import { getSource } from '../../api';
import { errorMessage, publishedLabel, sourceTitle } from '../../lib/format';
import { formatTime } from '../../lib/time';
import { usePolling } from '../../lib/usePolling';
import type { KeyQuote, SourceDetail } from '../../types';
import { StatusBadge } from '../sources/StatusBadge';
import { useYouTubePlayer } from './useYouTubePlayer';
import './source-page.css';

export function SourcePage({ onCollectionSeen }: { onCollectionSeen: (collectionId: string) => void }) {
  const { id } = useParams();
  const sourceId = Number(id);
  const valid = Number.isInteger(sourceId) && sourceId > 0;
  const [source, setSource] = useState<SourceDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const s = await getSource(sourceId);
      setSource(s);
      setError(null);
    } catch (e) {
      setError(errorMessage(e));
    }
  }, [sourceId]);

  useEffect(() => {
    setSource(null);
    if (valid) void load();
  }, [valid, load]);

  const collectionId = source?.collection_id;
  useEffect(() => {
    if (collectionId) onCollectionSeen(collectionId);
  }, [collectionId, onCollectionSeen]);

  const processing = !!source && source.status !== 'ready' && source.status !== 'failed';
  usePolling(load, 3000, processing);

  if (!valid) return <p className="error">Invalid source id.</p>;
  if (!source) {
    return error ? (
      <div className="banner error-banner" role="alert">
        Could not load this source: {error}
      </div>
    ) : (
      <p className="muted">Loading source…</p>
    );
  }

  const meta = [source.host, publishedLabel(source.published_at)];
  if (source.duration_s != null) meta.push(formatTime(source.duration_s));

  return (
    <article className="source-page">
      <p className="no-print">
        <Link to={`/c/${encodeURIComponent(source.collection_id)}/sources`}>← All sources</Link>
      </p>
      <h2>{sourceTitle(source)}</h2>
      <p className="meta">
        {meta.filter(Boolean).join(' · ')} ·{' '}
        <a href={source.url} target="_blank" rel="noopener noreferrer">
          Original {source.type === 'youtube' ? 'video' : 'page'}
        </a>
      </p>
      {error && (
        <div className="banner error-banner" role="alert">
          Refresh failed: {error}
        </div>
      )}
      {source.status !== 'ready' && (
        <div className="card" role="status">
          <p className="row">
            Status: <StatusBadge status={source.status} />
          </p>
          {source.status === 'failed' ? (
            <p className="error">{source.error ?? 'Ingest failed.'}</p>
          ) : (
            <p className="muted">This source is still being processed. The page updates every 3 seconds.</p>
          )}
        </div>
      )}
      {source.type === 'youtube' ? <YouTubeSource source={source} /> : <WebSource source={source} />}
    </article>
  );
}

function Overview({ text }: { text: string | null }) {
  if (!text) return null;
  return (
    <section aria-labelledby="overview-title">
      <h3 id="overview-title">Overview</h3>
      <p>{text}</p>
    </section>
  );
}

function Tags({ tags }: { tags: string[] }) {
  if (tags.length === 0) return null;
  return (
    <ul className="list-reset tags" aria-label="Tags">
      {tags.map((t) => (
        <li key={t} className="badge">
          {t}
        </li>
      ))}
    </ul>
  );
}

function QuoteBody({ quote }: { quote: KeyQuote }) {
  return (
    <>
      <span className="row quote-badges">
        <span className="badge verbatim">verbatim</span>
        {quote.is_advice && <span className="badge advice">advice</span>}
      </span>
      <blockquote>“{quote.quote}”</blockquote>
    </>
  );
}

/* ---------- YouTube ---------- */

function parseT(value: string | null): number | null {
  if (value === null || value === '') return null;
  const n = Number(value);
  return Number.isFinite(n) && n >= 0 ? n : null;
}

function TimeButton({ s, label, onPlay }: { s: number; label?: string; onPlay: (seconds: number) => void }) {
  return (
    <button type="button" className="ts-button" onClick={() => onPlay(s)} aria-label={`Play from ${formatTime(s)}`}>
      {label ?? formatTime(s)}
    </button>
  );
}

function YouTubeSource({ source }: { source: SourceDetail }) {
  const [params] = useSearchParams();
  const t = parseT(params.get('t'));
  const { containerRef, seek, error } = useYouTubePlayer(source.ext_id, t ?? 0);
  const playerBoxRef = useRef<HTMLDivElement>(null);

  const play = useCallback(
    (seconds: number) => {
      seek(seconds);
      playerBoxRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    },
    [seek],
  );

  // Initial ?t= is passed as the player's start time; later changes (another "Play here" link) seek.
  const lastT = useRef(t);
  useEffect(() => {
    if (t !== null && t !== lastT.current) play(t);
    lastT.current = t;
  }, [t, play]);

  return (
    <>
      {source.ext_id ? (
        <div className="player-box" ref={playerBoxRef}>
          <div className="player" ref={containerRef} />
          {error && <p className="error">{error}</p>}
        </div>
      ) : (
        <p className="muted">No video id yet, so the player is not available.</p>
      )}

      <Overview text={source.overview} />

      {source.chapters.length > 0 && (
        <section aria-labelledby="chapters-title">
          <h3 id="chapters-title">Chapters</h3>
          <ol className="list-reset">
            {source.chapters.map((c) => (
              <li key={c.id} className="chapter">
                <TimeButton s={c.start_s} label={`${formatTime(c.start_s)}–${formatTime(c.end_s)}`} onPlay={play} />
                <div>
                  <strong>{c.title}</strong>
                  <p>{c.summary}</p>
                </div>
              </li>
            ))}
          </ol>
        </section>
      )}

      {source.key_quotes.length > 0 && (
        <section aria-labelledby="quotes-title">
          <h3 id="quotes-title">Key quotes</h3>
          <ul className="list-reset">
            {source.key_quotes.map((q) => (
              <li key={q.id} className="card quote">
                <div className="row">
                  <TimeButton s={q.ts_s} onPlay={play} />
                  <a href={q.deep_link} target="_blank" rel="noopener noreferrer">
                    Open on YouTube
                  </a>
                </div>
                <QuoteBody quote={q} />
              </li>
            ))}
          </ul>
        </section>
      )}

      {source.segments.length > 0 && (
        <section aria-labelledby="timeline-title">
          <h3 id="timeline-title">Minute timeline</h3>
          <ol className="list-reset timeline">
            {source.segments.map((s) => (
              <li key={s.id} id={`seg-${s.id}`} className="timeline-row">
                <TimeButton s={s.start_s} onPlay={play} />
                <div className="timeline-body">
                  <p>{s.summary}</p>
                  <Tags tags={s.tags} />
                  <details>
                    <summary>Transcript</summary>
                    <p className="raw-text">{s.text}</p>
                  </details>
                </div>
              </li>
            ))}
          </ol>
        </section>
      )}
    </>
  );
}

/* ---------- Web ---------- */

function WebSource({ source }: { source: SourceDetail }) {
  const { hash } = useLocation();
  const target = hash ? decodeURIComponent(hash.slice(1)) : '';
  const segmentCount = source.segments.length;

  useEffect(() => {
    if (!target || segmentCount === 0) return;
    const el = document.getElementById(target);
    if (!el) return;
    el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    el.focus({ preventScroll: true });
  }, [target, segmentCount]);

  return (
    <>
      <Overview text={source.overview} />

      {source.chapters.length > 0 && (
        <section aria-labelledby="chapters-title">
          <h3 id="chapters-title">Outline</h3>
          <ol>
            {source.chapters.map((c) => (
              <li key={c.id}>
                <strong>{c.title}</strong> {c.summary}
              </li>
            ))}
          </ol>
        </section>
      )}

      {source.key_quotes.length > 0 && (
        <section aria-labelledby="quotes-title">
          <h3 id="quotes-title">Key quotes</h3>
          <ul className="list-reset">
            {source.key_quotes.map((q) => (
              <li key={q.id} className="card quote">
                <div className="row">
                  <Link to={{ hash: `#seg-${q.segment_id}` }}>Go to section</Link>
                  <a href={q.deep_link} target="_blank" rel="noopener noreferrer">
                    Open on page
                  </a>
                </div>
                <QuoteBody quote={q} />
              </li>
            ))}
          </ul>
        </section>
      )}

      {segmentCount > 0 && (
        <section aria-labelledby="sections-title">
          <h3 id="sections-title">Sections</h3>
          {source.segments.map((s) => (
            <section
              key={s.id}
              id={`seg-${s.id}`}
              tabIndex={-1}
              className={`card web-section${target === `seg-${s.id}` ? ' is-target' : ''}`}
              aria-labelledby={`seg-${s.id}-title`}
            >
              <h4 id={`seg-${s.id}-title`}>{s.anchor || `Section ${s.ord + 1}`}</h4>
              <p>{s.summary}</p>
              <Tags tags={s.tags} />
              <details>
                <summary>Page text</summary>
                <p className="raw-text">{s.text}</p>
              </details>
              <a href={s.deep_link} target="_blank" rel="noopener noreferrer">
                Open on page
              </a>
            </section>
          ))}
        </section>
      )}
    </>
  );
}
