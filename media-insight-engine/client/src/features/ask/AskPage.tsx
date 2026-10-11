import { useEffect, useId, useRef, useState, type FormEvent } from 'react';
import { ApiError, ask, listSources } from '../../api';
import { errorMessage, sourceTitle } from '../../lib/format';
import { Spinner } from '../../lib/Spinner';
import type { AskFilters, SourceSummary } from '../../types';
import { useCollection } from '../collections/CollectionLayout';
import { AnswerView } from './AnswerView';
import { clearChat, loadChat, saveChat, type ChatTurn as Turn } from './chatStorage';
import { SaveToNotes } from './SaveToNotes';
import './ask.css';

const MAX_HISTORY = 10;

export function AskPage() {
  const collection = useCollection();
  const cid = collection.id;
  // Restored from sessionStorage, so the chat survives "Play here" and coming back (the page remounts per college).
  const [turns, setTurns] = useState<Turn[]>(() => loadChat(cid));
  const [question, setQuestion] = useState('');
  const [formError, setFormError] = useState<string | null>(null);
  const [scopeAll, setScopeAll] = useState(false);
  const [sources, setSources] = useState<SourceSummary[]>([]);
  const [sourceIds, setSourceIds] = useState<number[]>([]);
  const [tags, setTags] = useState<string[]>([]);
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const nextId = useRef(turns.reduce((max, t) => Math.max(max, t.id), 0) + 1);
  const lastTurnRef = useRef<HTMLLIElement>(null);
  const questionId = useId();

  useEffect(() => {
    // Only ready sources can be searched, so only they are offered as filters.
    listSources(cid).then(
      (all) => setSources(all.filter((s) => s.status === 'ready')),
      () => setSources([]),
    );
  }, [cid]);

  useEffect(() => saveChat(cid, turns), [cid, turns]);

  const busy = turns.some((t) => t.status === 'pending');
  const filterCount = sourceIds.length + tags.length + (dateFrom ? 1 : 0) + (dateTo ? 1 : 0);

  const run = async (turn: Turn) => {
    setTurns((ts) => ts.map((t) => (t.id === turn.id ? { ...t, status: 'pending', error: undefined } : t)));
    try {
      const response = await ask(turn.scope, { question: turn.question, history: turn.history, filters: turn.filters });
      setTurns((ts) => ts.map((t) => (t.id === turn.id ? { ...t, status: 'done', response } : t)));
    } catch (e) {
      // 502 = the model call failed; the server's detail says why (e.g. no API credits, key missing).
      const error = e instanceof ApiError && e.status === 502 ? `Answer failed: ${e.message}` : errorMessage(e);
      setTurns((ts) => ts.map((t) => (t.id === turn.id ? { ...t, status: 'error', error } : t)));
    }
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const q = question.trim();
    if (q.length < 3 || q.length > 2000) {
      setFormError('A question needs 3 to 2000 characters.');
      return;
    }
    setFormError(null);
    const filters: AskFilters = {};
    if (sourceIds.length) filters.source_ids = sourceIds;
    if (tags.length) filters.tags = tags;
    if (dateFrom) filters.date_from = dateFrom;
    if (dateTo) filters.date_to = dateTo;
    const history = turns
      .filter((t) => t.response)
      .slice(-MAX_HISTORY)
      .map((t) => ({ question: t.question, answer_md: t.response!.answer_md }));
    const turn: Turn = {
      id: nextId.current++,
      question: q,
      scope: scopeAll ? 'all' : cid,
      filters: filterCount ? filters : undefined,
      history,
      status: 'pending',
    };
    setTurns((ts) => [...ts, turn]);
    setQuestion('');
    void run(turn);
  };

  const turnCount = turns.length;
  useEffect(() => {
    if (turnCount) lastTurnRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, [turnCount]);

  const toggle = <T,>(list: T[], value: T) => (list.includes(value) ? list.filter((v) => v !== value) : [...list, value]);

  return (
    <div className="ask-page">
      <div className="row ask-head">
        <h2>Ask</h2>
        {turns.length > 0 && (
          <button
            type="button"
            onClick={() => {
              setTurns([]);
              clearChat(cid);
            }}
            disabled={busy}
          >
            New chat
          </button>
        )}
      </div>

      <fieldset className="scope">
        <legend>Search in</legend>
        <label>
          <input type="radio" name="scope" checked={!scopeAll} onChange={() => setScopeAll(false)} /> This college (
          {collection.name})
        </label>
        <label>
          <input type="radio" name="scope" checked={scopeAll} onChange={() => setScopeAll(true)} /> All colleges
        </label>
      </fieldset>

      <details className="filters">
        <summary>Filters{filterCount > 0 && ` (${filterCount} active)`}</summary>
        <fieldset>
          <legend>Sources{scopeAll && ` (${collection.name} only)`}</legend>
          {sources.length === 0 && <p className="muted">No ready sources.</p>}
          <div className="check-list">
            {sources.map((s) => (
              <label key={s.id}>
                <input
                  type="checkbox"
                  checked={sourceIds.includes(s.id)}
                  onChange={() => setSourceIds((ids) => toggle(ids, s.id))}
                />{' '}
                {sourceTitle(s)}
              </label>
            ))}
          </div>
        </fieldset>
        <fieldset>
          <legend>Tags</legend>
          <div className="check-list tag-list">
            {collection.lens_tags.map((t) => (
              <label key={t}>
                <input type="checkbox" checked={tags.includes(t)} onChange={() => setTags((ts) => toggle(ts, t))} /> {t}
              </label>
            ))}
          </div>
        </fieldset>
        <div className="row">
          <label className="field">
            Published from
            <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
          </label>
          <label className="field">
            Published to
            <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
          </label>
        </div>
        <button
          type="button"
          onClick={() => {
            setSourceIds([]);
            setTags([]);
            setDateFrom('');
            setDateTo('');
          }}
          disabled={filterCount === 0}
        >
          Clear filters
        </button>
      </details>

      <ol className="list-reset turns" aria-live="polite">
        {turns.map((t, i) => (
          <li key={t.id} className="turn" ref={i === turns.length - 1 ? lastTurnRef : undefined}>
            <p className="turn-question">
              <span className="visually-hidden">You asked: </span>
              {t.question}
              {t.scope === 'all' && <span className="badge">all colleges</span>}
            </p>
            {t.status === 'pending' && <Spinner label="Searching your sources… (usually 3–10 seconds)" />}
            {t.status === 'error' && (
              <div className="banner error-banner" role="alert">
                {t.error}{' '}
                <button type="button" onClick={() => void run(t)} disabled={busy}>
                  Try again
                </button>
              </div>
            )}
            {t.status === 'done' && t.response && (
              <div className="card">
                <AnswerView
                  idPrefix={`turn-${t.id}`}
                  label={t.response.label}
                  answerMd={t.response.answer_md}
                  coverage={t.response.coverage}
                  citations={t.response.citations}
                  notCovered={t.response.not_covered}
                  closest={t.response.closest}
                  staleWarning={t.response.stale_warning}
                  conflicts={t.response.conflicts}
                  showCollection={t.scope === 'all'}
                >
                  <SaveToNotes
                    notesPath={`/c/${encodeURIComponent(cid)}/notes${t.scope === 'all' ? '?scope=all' : ''}`}
                    note={{
                      collection_id: t.scope,
                      question: t.question,
                      answer_md: t.response.answer_md,
                      coverage: t.response.coverage,
                      citations: t.response.citations,
                    }}
                  />
                </AnswerView>
              </div>
            )}
          </li>
        ))}
      </ol>

      <form className="ask-form" onSubmit={submit}>
        <label htmlFor={questionId} className="field">
          {turns.length ? 'Follow-up question' : 'Your question'}
        </label>
        <textarea
          id={questionId}
          rows={3}
          value={question}
          maxLength={2000}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) e.currentTarget.form?.requestSubmit();
          }}
          placeholder="e.g. What does the college look for in the why-this-major essay?"
        />
        {formError && (
          <p className="error" role="alert">
            {formError}
          </p>
        )}
        <div className="row">
          <button type="submit" className="primary" disabled={busy}>
            {busy ? 'Waiting for answer…' : 'Ask'}
          </button>
          <span className="meta">Ctrl+Enter to send</span>
        </div>
      </form>
    </div>
  );
}
