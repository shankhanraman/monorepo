import { useId, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { createNote } from '../../api';
import { errorMessage } from '../../lib/format';
import type { NoteCreate } from '../../types';

interface Props {
  /** Note without the comment; `citations` are passed through unchanged. */
  note: Omit<NoteCreate, 'comment'>;
  notesPath: string;
}

export function SaveToNotes({ note, notesPath }: Props) {
  const [comment, setComment] = useState('');
  const [state, setState] = useState<'idle' | 'saving' | 'saved'>('idle');
  const [error, setError] = useState<string | null>(null);
  const inputId = useId();

  const save = async (e: FormEvent) => {
    e.preventDefault();
    setState('saving');
    setError(null);
    try {
      await createNote({ ...note, comment: comment.trim() || null });
      setState('saved');
    } catch (err) {
      setError(errorMessage(err));
      setState('idle');
    }
  };

  if (state === 'saved') {
    return (
      <p className="save-note" role="status">
        Saved. <Link to={notesPath}>Open notes</Link>
      </p>
    );
  }
  return (
    <form className="row save-note" onSubmit={save}>
      <label htmlFor={inputId} className="visually-hidden">
        Comment for this note (optional)
      </label>
      <input
        id={inputId}
        value={comment}
        onChange={(e) => setComment(e.target.value)}
        placeholder="Comment (optional)"
        maxLength={2000}
      />
      <button type="submit" disabled={state === 'saving'}>
        {state === 'saving' ? 'Saving…' : 'Save to notes'}
      </button>
      {error && (
        <span className="error" role="alert">
          {error}
        </span>
      )}
    </form>
  );
}
