import { useCallback, useEffect, useState } from 'react';
import { Link, Navigate, NavLink, Route, Routes, useMatch } from 'react-router-dom';
import { listCollections } from './api';
import { errorMessage } from './lib/format';
import type { Collection } from './types';
import { CollectionLayout } from './features/collections/CollectionLayout';
import { CollectionPicker } from './features/collections/CollectionPicker';
import { SourcesPage } from './features/sources/SourcesPage';
import { SourcePage } from './features/source-page/SourcePage';
import { AskPage } from './features/ask/AskPage';
import { NotesPage } from './features/notes/NotesPage';
import { BanksPage } from './features/question-bank/BanksPage';
import { BankReportPage } from './features/question-bank/BankReportPage';
import './features/collections/collections.css';

const NAV = [
  { to: 'sources', label: 'Sources' },
  { to: 'ask', label: 'Ask' },
  { to: 'banks', label: 'Question Bank' },
  { to: 'notes', label: 'Notes' },
];

export default function App() {
  const [collections, setCollections] = useState<Collection[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastCid, setLastCid] = useState<string | null>(null);

  const load = useCallback(() => {
    setError(null);
    listCollections().then(setCollections, (e: unknown) => setError(errorMessage(e)));
  }, []);
  useEffect(load, [load]);

  const routeCid = useMatch('/c/:cid/*')?.params.cid ?? null;
  const cid = routeCid ?? lastCid ?? collections?.[0]?.id ?? null;

  return (
    <>
      <header className="app-header no-print">
        <Link to="/" className="app-name">
          Media Insight Engine
        </Link>
        <CollectionPicker collections={collections ?? []} current={cid} />
        {cid && (
          <nav className="main-nav" aria-label="Main">
            {NAV.map((n) => (
              <NavLink key={n.to} to={`/c/${encodeURIComponent(cid)}/${n.to}`}>
                {n.label}
              </NavLink>
            ))}
          </nav>
        )}
      </header>
      <main className="page">
        {error && (
          <div className="banner error-banner" role="alert">
            Could not load colleges: {error}{' '}
            <button type="button" onClick={load}>
              Retry
            </button>
          </div>
        )}
        <Routes>
          <Route path="/" element={<Home collections={collections} />} />
          <Route path="/c/:cid" element={<CollectionLayout collections={collections} onSelect={setLastCid} />}>
            <Route index element={<Navigate to="sources" replace />} />
            <Route path="sources" element={<SourcesPage />} />
            <Route path="ask" element={<AskPage />} />
            <Route path="banks" element={<BanksPage />} />
            <Route path="banks/runs/:runId" element={<BankReportPage />} />
            <Route path="notes" element={<NotesPage />} />
          </Route>
          <Route path="/sources/:id" element={<SourcePage onCollectionSeen={setLastCid} />} />
          <Route path="*" element={<p>Page not found. <Link to="/">Go home</Link></p>} />
        </Routes>
      </main>
    </>
  );
}

function Home({ collections }: { collections: Collection[] | null }) {
  if (!collections) return <p className="muted">Loading colleges…</p>;
  if (collections.length === 0) return <p>No colleges are configured yet. Add a file to config/collections/ on the server.</p>;
  return <Navigate to={`/c/${encodeURIComponent(collections[0].id)}/sources`} replace />;
}
