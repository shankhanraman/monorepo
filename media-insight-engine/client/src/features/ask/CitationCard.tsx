import { Link } from 'react-router-dom';
import { publishedLabel } from '../../lib/format';
import { appLinkText, openLinkText } from '../../lib/sourceLabels';
import type { Citation } from '../../types';

interface Props {
  citation: Citation;
  id?: string;
  active?: boolean;
  /** Show which college the citation came from (questions asked across all colleges). */
  showCollection?: boolean;
  /** "Closest moments": not part of an answer, rendered quieter and without [n]. */
  secondary?: boolean;
}

export function CitationCard({ citation: c, id, active, showCollection, secondary }: Props) {
  return (
    <article
      id={id}
      tabIndex={-1}
      className={`citation-card${active ? ' is-active' : ''}${secondary ? ' is-secondary' : ''}`}
    >
      <h4 className="citation-title">
        {!secondary && <span className="cite-n">[{c.n}]</span>} {c.source_title}
      </h4>
      <p className="meta">
        {publishedLabel(c.published_at)} · {c.label}
        {c.stale && (
          <span className="stale" title="Older than 18 months or date unknown: verify on the official site">
            {' '}
            ⚠ <span className="visually-hidden">possibly outdated</span>
          </span>
        )}
        {showCollection && <span className="badge citation-college">{c.collection_id}</span>}
      </p>
      <p className="snippet">{c.snippet}</p>
      <p className="row citation-links">
        <a href={c.deep_link} target="_blank" rel="noopener noreferrer">
          {openLinkText(c.source_type)}
          <span className="visually-hidden"> (new tab)</span>
        </a>
        <Link to={c.app_link}>{appLinkText(c.source_type)}</Link>
      </p>
    </article>
  );
}
