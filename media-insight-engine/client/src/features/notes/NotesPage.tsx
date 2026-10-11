import { useCallback, useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { deleteNote, listNotes } from '../../api';
import { errorMessage, formatDateTime } from '../../lib/format';
import type { Note } from '../../types';
import { AnswerView } from '../ask/AnswerView';
import { useCollection } from '../collections/CollectionLayout';
import './notes.css';

export function NotesPage() {
  const collection = useCollection();
  const [params, setParams] = useSearchParams();
  const scopeAll = params.get('scope') === 'all';
  const filter = scopeAll ? 'all' : collection.id;
  const [notes, setNotes] = useState<Note[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setNotes(null);
    try {
      setNotes(await listNotes(filter));
      setError(null);
    } catch (e) {
      setError(errorMessage(e));
    }
  }, [filter]);
  useEffect(() => {
    void load();
  }, [load]);

  const remove = async (note: Note) => {
    if (!window.confirm(`Delete the note "${note.question}"?`)) return;
    try {
      await deleteNote(note.id);
      setNotes((ns) => ns?.filter((n) => n.id !== note.id) ?? null);
    } catch (e) {
      setError(errorMessage(e));
    }
  };

  return (
    <div>
      <h2>Notes</h2>
      <fieldset className="scope">
        <legend>Show notes from</legend>
        <label>
          <input type="radio" name="notes-scope" checked={!scopeAll} onChange={() => setParams({})} />{' '}
          {collection.name} questions
        </label>
        <label>
          <input type="radio" name="notes-scope" checked={scopeAll} onChange={() => setParams({ scope: 'all' })} />{' '}
          All-colleges questions
        </label>
      </fieldset>

      {error && (
        <div className="banner error-banner" role="alert">
          {error}
        </div>
      )}
      {notes === null && !error && <p className="muted">Loading notes…</p>}
      {notes?.length === 0 && <p className="muted">No notes yet. Use "Save to notes" under an answer in Ask.</p>}
      <ul className="list-reset">
        {notes?.map((n) => (
          <li key={n.id} className="card note">
            <div className="row note-head">
              <h3>{n.question}</h3>
              <button type="button" className="danger" onClick={() => void remove(n)}>
                Delete<span className="visually-hidden"> note: {n.question}</span>
              </button>
            </div>
            <p className="meta">Saved {formatDateTime(n.created_at)}</p>
            {n.comment && <p className="note-comment">{n.comment}</p>}
            <AnswerView
              idPrefix={`note-${n.id}`}
              label="Summary of sources"
              answerMd={n.answer_md}
              coverage={n.coverage}
              citations={n.citations}
              showCollection={n.collection_id === 'all'}
            />
          </li>
        ))}
      </ul>
    </div>
  );
}
