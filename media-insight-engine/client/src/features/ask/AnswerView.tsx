import { useState, type ReactNode } from 'react';
import { AnswerText } from '../../lib/AnswerText';
import { CoverageBadge } from '../../lib/CoverageBadge';
import type { Citation, Coverage } from '../../types';
import { CitationCard } from './CitationCard';
import './ask.css';

interface Props {
  /** Unique per answer on the page; used for citation card ids. */
  idPrefix: string;
  label?: string;
  answerMd: string;
  coverage: Coverage | null;
  citations: Citation[];
  notCovered?: boolean;
  closest?: Citation[];
  staleWarning?: string | null;
  conflicts?: string | null;
  showCollection?: boolean;
  /** Extra controls under the answer (e.g. Save to notes). */
  children?: ReactNode;
}

/** An answer rendered per api-contract.md §3 "How to render an answer". */
export function AnswerView(props: Props) {
  const { idPrefix, label, answerMd, coverage, citations, notCovered, closest = [], showCollection } = props;
  const [activeN, setActiveN] = useState<number | null>(null);
  const cardId = (n: number) => `${idPrefix}-cite-${n}`;

  const showCitation = (n: number) => {
    setActiveN(n);
    const el = document.getElementById(cardId(n));
    el?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    el?.focus({ preventScroll: true });
  };

  return (
    <div className="answer">
      <div className="row answer-head">
        {label && <span className="answer-label">{label}</span>}
        <CoverageBadge coverage={coverage} />
      </div>
      {props.staleWarning && <p className="banner warning">⚠ {props.staleWarning}</p>}
      {props.conflicts && <p className="banner warning">Sources disagree: {props.conflicts}</p>}

      {notCovered ? (
        <>
          <p className="not-covered">Not covered in your sources</p>
          {closest.length > 0 && (
            <section className="closest" aria-label="Closest moments">
              <h4>Closest moments</h4>
              {closest.map((c) => (
                <CitationCard key={c.n} citation={c} secondary showCollection={showCollection} />
              ))}
            </section>
          )}
        </>
      ) : (
        <>
          <AnswerText text={answerMd} known={citations.map((c) => c.n)} onCite={showCitation} />
          {citations.length > 0 && (
            <section className="citations" aria-label="Citations">
              {citations.map((c) => (
                <CitationCard
                  key={c.n}
                  id={cardId(c.n)}
                  citation={c}
                  active={activeN === c.n}
                  showCollection={showCollection}
                />
              ))}
            </section>
          )}
        </>
      )}
      {props.children}
    </div>
  );
}
