import { describe, expect, it } from 'vitest';
import type { AskResponse } from '../../types';
import { chatKey, clearChat, INTERRUPTED, loadChat, saveChat, type ChatStorage, type ChatTurn } from './chatStorage';

function memoryStorage(): ChatStorage & { data: Map<string, string> } {
  const data = new Map<string, string>();
  return {
    data,
    getItem: (k) => data.get(k) ?? null,
    setItem: (k, v) => void data.set(k, v),
    removeItem: (k) => void data.delete(k),
  };
}

const throwing: ChatStorage = {
  getItem: () => {
    throw new Error('SecurityError');
  },
  setItem: () => {
    throw new Error('QuotaExceededError');
  },
  removeItem: () => {
    throw new Error('SecurityError');
  },
};

const response: AskResponse = {
  question: 'Is the SAT required?',
  label: 'Answer',
  answer_md: 'Yes, testing is required [1].',
  coverage: 'strong',
  not_covered: false,
  citations: [],
  closest: [],
  stale_warning: null,
  conflicts: null,
  retried: false,
};

const done: ChatTurn = {
  id: 1,
  question: 'Is the SAT required?',
  scope: 'yale',
  filters: { tags: ['testing'] },
  history: [],
  status: 'done',
  response,
};
const failed: ChatTurn = {
  id: 2,
  question: 'And the ACT?',
  scope: 'all',
  filters: undefined,
  history: [{ question: done.question, answer_md: response.answer_md }],
  status: 'error',
  error: 'Answer failed: no credits',
};
const pending: ChatTurn = { ...failed, id: 3, question: 'What about AP scores?', status: 'pending', error: undefined };

describe('chat storage', () => {
  it('round-trips done and error turns under mie.chat.<cid>', () => {
    const s = memoryStorage();
    saveChat('yale', [done, failed], s);
    expect([...s.data.keys()]).toEqual([chatKey('yale')]);
    expect(chatKey('yale')).toBe('mie.chat.yale');
    expect(loadChat('yale', s)).toEqual([done, failed]);
  });

  it('keeps colleges apart', () => {
    const s = memoryStorage();
    saveChat('yale', [done], s);
    expect(loadChat('mit', s)).toEqual([]);
  });

  it('stores a pending turn as an interrupted error turn (so it offers "Try again")', () => {
    const s = memoryStorage();
    saveChat('yale', [done, pending], s);
    const restored = loadChat('yale', s);
    expect(restored).toHaveLength(2);
    expect(restored[1]).toMatchObject({ id: 3, question: pending.question, status: 'error', error: INTERRUPTED });
    expect(restored[1].history).toEqual(pending.history);
    expect(s.data.get(chatKey('yale'))).not.toContain('"pending"');
  });

  it('turns a pending turn found in storage into an error turn too', () => {
    const s = memoryStorage();
    s.data.set(chatKey('yale'), JSON.stringify([pending]));
    expect(loadChat('yale', s)).toEqual([{ ...pending, status: 'error', error: INTERRUPTED, response: undefined }]);
  });

  it('gives an empty chat for missing or corrupt data', () => {
    const s = memoryStorage();
    expect(loadChat('yale', s)).toEqual([]);
    for (const bad of ['{not json', '"text"', '42', 'null', '{"turns": []}']) {
      s.data.set(chatKey('yale'), bad);
      expect(loadChat('yale', s)).toEqual([]);
    }
  });

  it('drops turns with the wrong shape and keeps the valid ones', () => {
    const s = memoryStorage();
    const brokenDone = { ...done, id: 9, response: { answer_md: 'x' } }; // no citations
    const noId = { ...failed, id: 'x' };
    const badStatus = { ...failed, id: 10, status: 'thinking' };
    s.data.set(chatKey('yale'), JSON.stringify([brokenDone, done, noId, null, badStatus, 'turn']));
    expect(loadChat('yale', s)).toEqual([done]);
  });

  it('removes the key for an empty chat and on clearChat ("New chat")', () => {
    const s = memoryStorage();
    saveChat('yale', [done], s);
    saveChat('yale', [], s);
    expect(s.data.has(chatKey('yale'))).toBe(false);
    saveChat('yale', [done], s);
    clearChat('yale', s);
    expect(s.data.has(chatKey('yale'))).toBe(false);
  });

  it('never throws when storage throws or is unavailable', () => {
    expect(() => saveChat('yale', [done], throwing)).not.toThrow();
    expect(() => clearChat('yale', throwing)).not.toThrow();
    expect(loadChat('yale', throwing)).toEqual([]);
    expect(loadChat('yale', null)).toEqual([]);
    expect(() => saveChat('yale', [done], null)).not.toThrow();
    // default storage: no `window` in the test environment
    expect(loadChat('yale')).toEqual([]);
    expect(() => saveChat('yale', [done])).not.toThrow();
  });
});
