import { useLocation, useNavigate } from 'react-router-dom';
import type { Collection } from '../../types';

/** Pages that exist for every college; switching college keeps the user on the same kind of page. */
const SECTIONS = ['sources', 'ask', 'banks', 'notes'];

export function CollectionPicker({ collections, current }: { collections: Collection[]; current: string | null }) {
  const navigate = useNavigate();
  const { pathname } = useLocation();

  const onChange = (id: string) => {
    const section = pathname.match(/^\/c\/[^/]+\/([^/]+)/)?.[1];
    navigate(`/c/${encodeURIComponent(id)}/${section && SECTIONS.includes(section) ? section : 'sources'}`);
  };

  return (
    <label className="college-picker">
      <span>College</span>
      <select value={current ?? ''} onChange={(e) => onChange(e.target.value)} disabled={collections.length === 0}>
        {current && !collections.some((c) => c.id === current) && <option value={current}>{current}</option>}
        {collections.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name}
          </option>
        ))}
      </select>
    </label>
  );
}
