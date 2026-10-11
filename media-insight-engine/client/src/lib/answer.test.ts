import { describe, expect, it } from 'vitest';
import { parseAnswer } from './answer';

describe('parseAnswer', () => {
  it('turns known [n] markers into citation parts', () => {
    expect(parseAnswer('Officers want specifics [1]. And resources [2].', [1, 2])).toEqual([
      [
        { kind: 'text', text: 'Officers want specifics ' },
        { kind: 'cite', n: 1 },
        { kind: 'text', text: '. And resources ' },
        { kind: 'cite', n: 2 },
        { kind: 'text', text: '.' },
      ],
    ]);
  });

  it('keeps unknown markers as literal text', () => {
    expect(parseAnswer('See [1] and [7].', [1])).toEqual([
      [
        { kind: 'text', text: 'See ' },
        { kind: 'cite', n: 1 },
        { kind: 'text', text: ' and [7].' },
      ],
    ]);
    expect(parseAnswer('Nothing [3]', [])).toEqual([[{ kind: 'text', text: 'Nothing [3]' }]]);
  });

  it('handles adjacent markers like [1][2]', () => {
    expect(parseAnswer('Both agree [1][2].', [1, 2])).toEqual([
      [
        { kind: 'text', text: 'Both agree ' },
        { kind: 'cite', n: 1 },
        { kind: 'cite', n: 2 },
        { kind: 'text', text: '.' },
      ],
    ]);
  });

  it('splits paragraphs on blank lines and drops empty ones', () => {
    const out = parseAnswer('First [1].\n\nSecond [2].\r\n\r\n\n  \nThird.\n', [1, 2]);
    expect(out).toHaveLength(3);
    expect(out[0]).toEqual([{ kind: 'text', text: 'First ' }, { kind: 'cite', n: 1 }, { kind: 'text', text: '.' }]);
    expect(out[1]).toEqual([{ kind: 'text', text: 'Second ' }, { kind: 'cite', n: 2 }, { kind: 'text', text: '.' }]);
    expect(out[2]).toEqual([{ kind: 'text', text: 'Third.' }]);
  });

  it('keeps a single newline inside a paragraph', () => {
    expect(parseAnswer('line one\nline two', [])).toEqual([[{ kind: 'text', text: 'line one\nline two' }]]);
  });

  it('ignores non-numeric brackets and handles marker-only text', () => {
    expect(parseAnswer('[a] [1]', [1])).toEqual([[{ kind: 'text', text: '[a] ' }, { kind: 'cite', n: 1 }]]);
    expect(parseAnswer('', [1])).toEqual([]);
  });
});
