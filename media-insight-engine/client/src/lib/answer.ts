export type AnswerPart = { kind: 'text'; text: string } | { kind: 'cite'; n: number };

const MARKER = /\[(\d+)\]/g;

/**
 * Split `answer_md` (plain text with blank-line paragraphs and `[n]` markers) into paragraphs of parts.
 * Only markers whose `n` is in `known` become citation parts; any other marker stays literal text.
 */
export function parseAnswer(text: string, known: Iterable<number>): AnswerPart[][] {
  const ns = new Set(known);
  return text
    .replace(/\r\n?/g, '\n')
    .split(/\n[ \t]*\n/)
    .map((p) => p.trim())
    .filter((p) => p.length > 0)
    .map((paragraph) => {
      const parts: AnswerPart[] = [];
      const pushText = (t: string) => {
        if (!t) return;
        const last = parts[parts.length - 1];
        if (last && last.kind === 'text') last.text += t;
        else parts.push({ kind: 'text', text: t });
      };
      let pos = 0;
      for (const m of paragraph.matchAll(MARKER)) {
        const n = Number(m[1]);
        const at = m.index ?? 0;
        pushText(paragraph.slice(pos, at));
        if (ns.has(n)) parts.push({ kind: 'cite', n });
        else pushText(m[0]);
        pos = at + m[0].length;
      }
      pushText(paragraph.slice(pos));
      return parts;
    });
}
