import { Fragment } from 'react';
import { parseAnswer } from './answer';

interface Props {
  text: string;
  /** Citation numbers that exist; only these markers become buttons. */
  known: number[];
  /** Called when a `[n]` marker is activated. */
  onCite: (n: number) => void;
}

/** Renders `answer_md`: paragraphs on blank lines, `[n]` markers as buttons that jump to citation n. */
export function AnswerText({ text, known, onCite }: Props) {
  const paragraphs = parseAnswer(text, known);
  return (
    <div className="answer-text">
      {paragraphs.map((parts, i) => (
        <p key={i}>
          {parts.map((part, j) =>
            part.kind === 'text' ? (
              <Fragment key={j}>{part.text}</Fragment>
            ) : (
              <button
                key={j}
                type="button"
                className="cite-marker"
                onClick={() => onCite(part.n)}
                aria-label={`Show citation ${part.n}`}
              >
                [{part.n}]
              </button>
            ),
          )}
        </p>
      ))}
    </div>
  );
}
