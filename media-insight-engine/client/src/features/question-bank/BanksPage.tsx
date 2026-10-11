import { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ApiError, deleteQuestionBank, listQuestionBanks, runQuestionBank } from '../../api';
import { errorMessage, formatDateTime } from '../../lib/format';
import type { QuestionBank } from '../../types';
import { useCollection } from '../collections/CollectionLayout';
import { CreateBankForm } from './CreateBankForm';
import './question-bank.css';

export function BanksPage() {
  const collection = useCollection();
  const cid = collection.id;
  const navigate = useNavigate();
  const [banks, setBanks] = useState<QuestionBank[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rowErrors, setRowErrors] = useState<Record<number, string>>({});
  const [busyId, setBusyId] = useState<number | null>(null);

  const load = useCallback(async () => {
    try {
      setBanks(await listQuestionBanks(cid));
      setError(null);
    } catch (e) {
      setError(errorMessage(e));
    }
  }, [cid]);
  useEffect(() => {
    void load();
  }, [load]);

  const reportPath = (runId: number) => `/c/${encodeURIComponent(cid)}/banks/runs/${runId}`;
  const setRowError = (id: number, msg: string | null) =>
    setRowErrors(({ [id]: _old, ...rest }) => (msg ? { ...rest, [id]: msg } : rest));

  const run = async (bank: QuestionBank) => {
    setBusyId(bank.id);
    setRowError(bank.id, null);
    try {
      const started = await runQuestionBank(bank.id);
      navigate(reportPath(started.id));
    } catch (e) {
      const busy = e instanceof ApiError && e.status === 409;
      setRowError(bank.id, busy ? `${e.message}. Open the last report to follow it.` : errorMessage(e));
      void load(); // refresh latest_run_id so the running report can be opened
    } finally {
      setBusyId(null);
    }
  };

  const remove = async (bank: QuestionBank) => {
    if (!window.confirm(`Delete the bank "${bank.name}" and all its reports?`)) return;
    setBusyId(bank.id);
    try {
      await deleteQuestionBank(bank.id);
      setBanks((bs) => bs?.filter((b) => b.id !== bank.id) ?? null);
    } catch (e) {
      setRowError(bank.id, errorMessage(e));
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div>
      <h2>{collection.name} question banks</h2>
      {error && (
        <div className="banner error-banner" role="alert">
          {error}
        </div>
      )}
      {banks === null && !error && <p className="muted">Loading banks…</p>}
      {banks?.length === 0 && <p className="muted">No banks yet. Create one below.</p>}
      <ul className="list-reset">
        {banks?.map((b) => (
          <li key={b.id} className="card bank">
            <h3>{b.name}</h3>
            <p className="meta">
              {b.questions.length} question{b.questions.length === 1 ? '' : 's'} · created {formatDateTime(b.created_at)}
            </p>
            <details>
              <summary>Questions</summary>
              <ol>
                {b.questions.map((q, i) => (
                  <li key={i}>{q}</li>
                ))}
              </ol>
            </details>
            <div className="row bank-actions">
              <button type="button" className="primary" onClick={() => void run(b)} disabled={busyId === b.id}>
                Run
              </button>
              {b.latest_run_id !== null && <Link to={reportPath(b.latest_run_id)}>Open last report</Link>}
              <button type="button" className="danger" onClick={() => void remove(b)} disabled={busyId === b.id}>
                Delete
              </button>
            </div>
            {rowErrors[b.id] && (
              <p className="error" role="alert">
                {rowErrors[b.id]}
              </p>
            )}
          </li>
        ))}
      </ul>
      <CreateBankForm collectionId={cid} onCreated={(bank) => setBanks((bs) => [bank, ...(bs ?? [])])} />
    </div>
  );
}
