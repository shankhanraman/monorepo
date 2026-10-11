import { useId, useRef, useState, type ChangeEvent, type FormEvent } from 'react';
import { createQuestionBank } from '../../api';
import { errorMessage } from '../../lib/format';
import type { QuestionBank } from '../../types';
import { parseQuestions } from './parseQuestions';

interface Props {
  collectionId: string;
  onCreated: (bank: QuestionBank) => void;
}

interface UploadedFile {
  name: string;
  text: string;
  csv: boolean;
}

export function CreateBankForm({ collectionId, onCreated }: Props) {
  const [name, setName] = useState('');
  const [text, setText] = useState('');
  const [file, setFile] = useState<UploadedFile | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const ids = { name: useId(), text: useId(), file: useId(), status: useId() };

  const hasInput = file !== null || text.trim() !== '';
  const parsed = file ? parseQuestions(file.text, file.csv ? 'csv' : 'text') : parseQuestions(text, 'text');

  const onFile = async (e: ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f) return;
    try {
      setFile({ name: f.name, text: await f.text(), csv: /\.csv$/i.test(f.name) || f.type === 'text/csv' });
    } catch (err) {
      setError(`Could not read ${f.name}: ${errorMessage(err)}`);
    }
  };

  const clearFile = () => {
    setFile(null);
    if (fileInput.current) fileInput.current.value = '';
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (parsed.error || !name.trim()) return;
    setSaving(true);
    setError(null);
    try {
      const bank = await createQuestionBank(collectionId, { name: name.trim(), questions: parsed.questions });
      setName('');
      setText('');
      clearFile();
      onCreated(bank);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <form className="card create-bank" onSubmit={submit} aria-labelledby="create-bank-title">
      <h3 id="create-bank-title">New question bank</h3>
      <label className="field" htmlFor={ids.name}>
        Name
      </label>
      <input
        id={ids.name}
        value={name}
        onChange={(e) => setName(e.target.value)}
        maxLength={200}
        required
        placeholder="e.g. Yale supplements + testing"
      />

      <label className="field" htmlFor={ids.text}>
        Questions, one per line
      </label>
      <textarea
        id={ids.text}
        rows={7}
        value={text}
        onChange={(e) => setText(e.target.value)}
        disabled={file !== null}
        aria-describedby={ids.status}
      />

      <div className="row file-row">
        <label htmlFor={ids.file}>Or upload a .txt or .csv file:</label>
        <input
          id={ids.file}
          ref={fileInput}
          type="file"
          accept=".txt,.csv,text/plain,text/csv"
          onChange={(e) => void onFile(e)}
        />
        {file && (
          <button type="button" onClick={clearFile}>
            Remove {file.name}
          </button>
        )}
      </div>
      {file && (
        <p className="meta">
          Using {file.name} {file.csv ? '(CSV: first column, header row "question" skipped)' : '(one question per line)'}.
        </p>
      )}

      <div id={ids.status} aria-live="polite">
        {hasInput &&
          (parsed.error ? (
            <p className="error">{parsed.error}</p>
          ) : (
            <details className="preview">
              <summary>
                {parsed.questions.length} question{parsed.questions.length === 1 ? '' : 's'} ready (preview)
              </summary>
              <ol>
                {parsed.questions.map((q, i) => (
                  <li key={i}>{q}</li>
                ))}
              </ol>
            </details>
          ))}
      </div>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <button type="submit" className="primary" disabled={saving || !hasInput || !!parsed.error || !name.trim()}>
        {saving ? 'Saving…' : 'Save bank'}
      </button>
    </form>
  );
}
