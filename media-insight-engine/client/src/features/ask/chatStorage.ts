import type { AskFilters, AskResponse, HistoryTurn } from '../../types';

/** One question and its answer in the Ask chat. */
export interface ChatTurn {
  id: number;
  question: string;
  /** Collection id or `all`. */
  scope: string;
  filters: AskFilters | undefined;
  history: HistoryTurn[];
  status: 'pending' | 'done' | 'error';
  response?: AskResponse;
  error?: string;
}

/** Shown for a question whose answer was still loading when the user left the page. */
export const INTERRUPTED = 'This question was interrupted before the answer arrived.';

/** The parts of `Storage` the helpers use (sessionStorage in the app, a fake in tests). */
export type ChatStorage = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;

export const chatKey = (collectionId: string) => `mie.chat.${collectionId}`;

/** sessionStorage, or null where it is unavailable (blocked site data, some private windows, tests). */
function sessionStore(): ChatStorage | null {
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

const isObject = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v);

/** Pending turns are never stored: they become error turns, which offer "Try again". */
const settle = (t: ChatTurn): ChatTurn =>
  t.status === 'pending' ? { ...t, status: 'error', response: undefined, error: INTERRUPTED } : t;

function isHistoryTurn(v: unknown): v is HistoryTurn {
  return isObject(v) && typeof v.question === 'string' && typeof v.answer_md === 'string';
}

/** Checks the shape the chat renders; anything else is dropped. */
function toTurn(v: unknown): ChatTurn | null {
  if (!isObject(v)) return null;
  const { id, question, scope, filters, history, status, response, error } = v;
  if (typeof id !== 'number' || !Number.isFinite(id)) return null;
  if (typeof question !== 'string' || typeof scope !== 'string') return null;
  if (filters !== undefined && !isObject(filters)) return null;
  if (!Array.isArray(history) || !history.every(isHistoryTurn)) return null;
  if (status !== 'pending' && status !== 'done' && status !== 'error') return null;
  if (error !== undefined && typeof error !== 'string') return null;
  if (status === 'done') {
    if (!isObject(response) || typeof response.answer_md !== 'string') return null;
    if (!Array.isArray(response.citations) || !Array.isArray(response.closest)) return null;
  }
  return settle({
    id,
    question,
    scope,
    filters: filters as AskFilters | undefined,
    history,
    status,
    response: status === 'done' ? (response as unknown as AskResponse) : undefined,
    error: status === 'error' ? (error ?? 'Something went wrong.') : undefined,
  });
}

/** The saved chat of a college. Missing, corrupt or unreadable data gives an empty chat. */
export function loadChat(collectionId: string, storage: ChatStorage | null = sessionStore()): ChatTurn[] {
  try {
    const raw = storage?.getItem(chatKey(collectionId));
    if (!raw) return [];
    const data: unknown = JSON.parse(raw);
    if (!Array.isArray(data)) return [];
    return data.map(toTurn).filter((t): t is ChatTurn => t !== null);
  } catch {
    return [];
  }
}

/** Saves the chat (pending turns as interrupted). An empty chat removes the key. Never throws (e.g. quota full). */
export function saveChat(
  collectionId: string,
  turns: readonly ChatTurn[],
  storage: ChatStorage | null = sessionStore(),
): void {
  try {
    if (!storage) return;
    if (turns.length === 0) storage.removeItem(chatKey(collectionId));
    else storage.setItem(chatKey(collectionId), JSON.stringify(turns.map(settle)));
  } catch {
    // storage full or blocked: the chat still works, it just won't survive leaving the page
  }
}

/** "New chat": forget the saved chat of a college. */
export const clearChat = (collectionId: string, storage: ChatStorage | null = sessionStore()): void =>
  saveChat(collectionId, [], storage);
