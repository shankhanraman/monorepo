import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { Link, useLocation, useParams, useSearchParams } from 'react-router-dom';
import { getSource } from '../../api';
import { errorMessage, publishedLabel, sourceTitle } from '../../lib/format';
import { openLinkText, pdfLinkText, pdfPage, progressPercent } from '../../lib/sourceLabels';
import { StaleBadge } from '../../lib/StaleBadge';
import { formatTime } from '../../lib/time';
import { usePolling } from '../../lib/usePolling';
import type { KeyQuote, Segment, SourceDetail, SourceType } from '../../types';
import { StatusBadge } from '../sources/StatusBadge';
import { useAudioPlayer } from './useAudioPlayer';
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

  const rest: string[] = [];
  if (source.duration_s != null) rest.push(formatTime(source.duration_s));
  if (source.feed_url) rest.push('from feed');
  const transcribePct = source.status === 'transcribing' ? progressPercent(source.progress) : null;

  return (
    <article className="source-page">
      <p className="no-print">
        <Link to={`/c/${encodeURIComponent(source.collection_id)}/sources`}>← All sources</Link>
      </p>
      <h2>{sourceTitle(source)}</h2>
      <p className="meta">
        {source.host && `${source.host} · `}
        {publishedLabel(source.published_at)}
        {source.stale && (
          <>
            {' '}
            <StaleBadge />
          </>
        )}
        {rest.map((m) => ` · ${m}`).join('')} ·{' '}
        <a href={source.url} target="_blank" rel="noopener noreferrer">
          Original {ORIGINAL_TEXT[source.type] ?? 'page'}
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
            Status: <StatusBadge status={source.status} progress={source.progress} />
          </p>
          {source.status === 'failed' ? (
            <p className="error">{source.error ?? 'Ingest failed.'}</p>
          ) : (
            <>
              {transcribePct !== null && (
                <p className="transcribe-progress">
                  <progress value={transcribePct} max={100} aria-label="Transcription progress" />
                  <span>Transcribing… {transcribePct} %</span>
                </p>
              )}
              <p className="muted">This source is still being processed. The page updates every 3 seconds.</p>
            </>
          )}
        </div>
      )}
      {source.type === 'youtube' ? (
        <YouTubeSource source={source} />
      ) : source.type === 'audio' ? (
        <AudioSource source={source} />
      ) : (
        <DocumentSource source={source} />
      )}
    </article>
  );
}

const ORIGINAL_TEXT: Record<SourceType, string> = { youtube: 'video', audio: 'episode', web: 'page', pdf: 'PDF' };

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

function ExternalLink({ href, className, children }: { href: string; className?: string; children: ReactNode }) {
  return (
    <a href={href} className={className} target="_blank" rel="noopener noreferrer">
      {children}
      <span className="visually-hidden"> (new tab)</span>
    </a>
  );
}

/* ---------- Time-based: YouTube and audio ---------- */

function parseT(value: string | null): number | null {
  if (value === null || value === '') return null;
  const n = Number(value);
  return Number.isFinite(n) && n >= 0 ? n : null;
}

/** `?t=<seconds>` of the current URL, or null. */
function useTParam(): number | null {
  const [params] = useSearchParams();
  return parseT(params.get('t'));
}

function TimeButton({ s, label, onPlay }: { s: number; label?: string; onPlay: (seconds: number) => void }) {
  return (
    <button type="button" className="ts-button" onClick={() => onPlay(s)} aria-label={`Play from ${formatTime(s)}`}>
      {label ?? formatTime(s)}
    </button>
  );
}

function YouTubeSource({ source }: { source: SourceDetail }) {
  const t = useTParam();
  // The initial ?t= is passed as the player's start time.
  const { containerRef, seek, error } = useYouTubePlayer(source.ext_id, t ?? 0);
  return (
    <TimeBasedView
      source={source}
      t={t}
      seek={seek}
      player={
        source.ext_id ? (
          <>
            <div className="player" ref={containerRef} />
            {error && <p className="error">{error}</p>}
          </>
        ) : null
      }
      noPlayerText="No video id yet, so the player is not available."
    />
  );
}

function AudioSource({ source }: { source: SourceDetail }) {
  const t = useTParam();
  // The initial ?t= sets the position and starts playback (if the browser allows it).
  const { audioRef, seek, error, onError, onCanPlay } = useAudioPlayer(t);
  return (
    <TimeBasedView
      source={source}
      t={t}
      seek={seek}
      player={
        source.media_url ? (
          <>
            <audio
              ref={audioRef}
              className="audio-player"
              controls
              preload="metadata"
              src={source.media_url}
              onError={onError}
              onCanPlay={onCanPlay}
              aria-label={`Audio: ${sourceTitle(source)}`}
            >
              <a href={source.media_url}>Download the audio</a>
            </audio>
            {error && <p className="error">{error}</p>}
          </>
        ) : null
      }
      noPlayerText="No playable audio yet, so the player is not available."
    />
  );
}

interface TimeBasedViewProps {
  source: SourceDetail;
  /** Current `?t=`. The player handles the first value; a later change seeks (another "Play here" link). */
  t: number | null;
  /** Moves the player to `seconds` and plays. */
  seek: (seconds: number) => void;
  /** The player element, or null when it is not available yet. */
  player: ReactNode;
  noPlayerText: string;
}

/** Player, overview, chapters, key quotes and minute timeline. Shared by YouTube and audio sources. */
function TimeBasedView({ source, t, seek, player, noPlayerText }: TimeBasedViewProps) {
  const playerBoxRef = useRef<HTMLDivElement>(null);
  const openText = openLinkText(source.type);

  const play = useCallback(
    (seconds: number) => {
      seek(seconds);
      playerBoxRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    },
    [seek],
  );

  const lastT = useRef(t);
  useEffect(() => {
    if (t !== null && t !== lastT.current) play(t);
    lastT.current = t;
  }, [t, play]);

  return (
    <>
      {player ? (
        <div className="player-box" ref={playerBoxRef}>
          {player}
        </div>
      ) : (
        <p className="muted">{noPlayerText}</p>
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
                  <ExternalLink href={q.deep_link}>{openText}</ExternalLink>
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
                  <ExternalLink href={s.deep_link} className="segment-link">
                    {openText}
                  </ExternalLink>
                </div>
              </li>
            ))}
          </ol>
        </section>
      )}
    </>
  );
}

/* ---------- Section-based: web and PDF ---------- */

function DocumentSource({ source }: { source: SourceDetail }) {
  const { hash } = useLocation();
  const target = hash ? decodeURIComponent(hash.slice(1)) : '';
  const segmentCount = source.segments.length;
  const isPdf = source.type === 'pdf';
  const linkText = (deepLink: string) => (isPdf ? pdfLinkText(deepLink) : 'Open on page');
  const heading = (s: Segment) => {
    if (s.anchor) return s.anchor; // "Page 3" for PDFs
    const page = isPdf ? pdfPage(s.deep_link) : null;
    return page !== null ? `Page ${page}` : `Section ${s.ord + 1}`;
  };

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
                  <ExternalLink href={q.deep_link}>{linkText(q.deep_link)}</ExternalLink>
                </div>
                <QuoteBody quote={q} />
              </li>
            ))}
          </ul>
        </section>
      )}

      {segmentCount > 0 && (
        <section aria-labelledby="sections-title">
          <h3 id="sections-title">{isPdf ? 'Pages' : 'Sections'}</h3>
          {source.segments.map((s) => (
            <section
              key={s.id}
              id={`seg-${s.id}`}
              tabIndex={-1}
              className={`card web-section${target === `seg-${s.id}` ? ' is-target' : ''}`}
              aria-labelledby={`seg-${s.id}-title`}
            >
              <h4 id={`seg-${s.id}-title`}>{heading(s)}</h4>
              <p>{s.summary}</p>
              <Tags tags={s.tags} />
              <details>
                <summary>Page text</summary>
                <p className="raw-text">{s.text}</p>
              </details>
              <ExternalLink href={s.deep_link}>{linkText(s.deep_link)}</ExternalLink>
            </section>
          ))}
        </section>
      )}
    </>
  );
}
