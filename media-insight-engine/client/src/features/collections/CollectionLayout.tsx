import { useEffect } from 'react';
import { Outlet, useOutletContext, useParams } from 'react-router-dom';
import type { Collection } from '../../types';

interface Props {
  collections: Collection[] | null;
  onSelect: (id: string) => void;
  /** Re-fetches `GET /collections` (e.g. after a sync changed `lens_tags` or `source_counts`). */
  reloadCollections: () => Promise<void>;
}

interface CollectionContext {
  collection: Collection;
  reloadCollections: () => Promise<void>;
}

/** Resolves `/c/:cid` to a collection and hands it to the page below via outlet context. */
export function CollectionLayout({ collections, onSelect, reloadCollections }: Props) {
  const { cid = '' } = useParams();
  useEffect(() => onSelect(cid), [cid, onSelect]);

  if (!collections) return <p className="muted">Loading colleges…</p>;
  const collection = collections.find((c) => c.id === cid);
  if (!collection) return <p className="error">Unknown college “{cid}”. Pick one from the list above.</p>;
  const context: CollectionContext = { collection, reloadCollections };
  // key: remount the page (and stop its polling) when the college changes
  return (
    <div key={cid}>
      <Outlet context={context} />
    </div>
  );
}

export const useCollection = () => useOutletContext<CollectionContext>().collection;
export const useReloadCollections = () => useOutletContext<CollectionContext>().reloadCollections;
