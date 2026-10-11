export const MIN_QUESTIONS = 1;
export const MAX_QUESTIONS = 100;
export const MIN_LENGTH = 3;
export const MAX_LENGTH = 2000;

export type QuestionFormat = 'text' | 'csv';

export interface ParseResult {
  questions: string[];
  /** Null when the list can be saved. */
  error: string | null;
}

/** Minimal RFC 4180 reader: commas, quoted fields with commas/newlines, `""` escapes, CRLF or LF. */
export function parseCsv(input: string): string[][] {
  const text = input.charCodeAt(0) === 0xfeff ? input.slice(1) : input;
  const rows: string[][] = [];
  let row: string[] = [];
  let field = '';
  let inQuotes = false;

  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (inQuotes) {
      if (c === '"' && text[i + 1] === '"') {
        field += '"';
        i++;
      } else if (c === '"') {
        inQuotes = false;
      } else {
        field += c;
      }
    } else if (c === '"' && field.trim() === '') {
      inQuotes = true;
      field = '';
    } else if (c === ',') {
      row.push(field);
      field = '';
    } else if (c === '\n' || c === '\r') {
      if (c === '\r' && text[i + 1] === '\n') i++;
      row.push(field);
      rows.push(row);
      row = [];
      field = '';
    } else {
      field += c;
    }
  }
  if (field !== '' || row.length > 0) {
    row.push(field);
    rows.push(row);
  }
  return rows;
}

function rawQuestions(text: string, format: QuestionFormat): string[] {
  if (format === 'text') return text.split(/\r\n|\r|\n/);
  const firstColumn = parseCsv(text).map((r) => r[0] ?? '');
  const headerAt = firstColumn.findIndex((v) => v.trim() !== '');
  if (headerAt >= 0 && firstColumn[headerAt].trim().toLowerCase() === 'question') firstColumn.splice(headerAt, 1);
  return firstColumn;
}

const preview = (q: string) => (q.length > 40 ? `${q.slice(0, 40)}…` : q);

/**
 * Turns pasted text (one question per line) or CSV (first column, optional "question" header)
 * into a clean list: trimmed, no empty lines, no exact duplicates, 1–100 questions of 3–2000 characters.
 */
export function parseQuestions(text: string, format: QuestionFormat = 'text'): ParseResult {
  const seen = new Set<string>();
  const questions: string[] = [];
  for (const raw of rawQuestions(text, format)) {
    const q = raw.trim();
    if (q === '' || seen.has(q)) continue;
    seen.add(q);
    questions.push(q);
  }

  if (questions.length < MIN_QUESTIONS) {
    return { questions, error: 'No questions found. Add at least one question, one per line.' };
  }
  if (questions.length > MAX_QUESTIONS) {
    return {
      questions,
      error: `Too many questions: ${questions.length}. A bank can hold at most ${MAX_QUESTIONS}.`,
    };
  }
  const problems = questions.flatMap((q, i) => {
    if (q.length < MIN_LENGTH) return [`question ${i + 1} ("${q}") is shorter than ${MIN_LENGTH} characters`];
    if (q.length > MAX_LENGTH)
      return [`question ${i + 1} ("${preview(q)}") is ${q.length} characters; the limit is ${MAX_LENGTH}`];
    return [];
  });
  if (problems.length > 0) {
    const shown = problems.slice(0, 3).join('; ');
    const more = problems.length > 3 ? ` (and ${problems.length - 3} more)` : '';
    return { questions, error: `Please fix: ${shown}${more}.` };
  }
  return { questions, error: null };
}
