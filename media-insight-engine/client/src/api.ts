import type {
  AskRequest,
  AskResponse,
  AskFilters,
  BankRun,
  Collection,
  Note,
  NoteCreate,
  QuestionBank,
  QuestionBankCreate,
  SourceDetail,
  SourceSummary,
  SyncLog,
} from './types';

export const API_URL: string = (import.meta.env.VITE_API_URL as string | undefined) || 'http://localhost:8003';

/** Error thrown for every non-2xx response. `message` is the server's `detail`. */
export class ApiError extends Error {
  readonly status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

/** `{"detail": "msg"}` or FastAPI's `{"detail": [{loc, msg, type}]}` → one readable string. */
function detailMessage(body: unknown, status: number): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d: { loc?: unknown[]; msg?: string }) => {
        const field = Array.isArray(d.loc) ? d.loc.filter((p) => p !== 'body').join('.') : '';
        return field ? `${field}: ${d.msg ?? ''}` : (d.msg ?? '');
      })
      .join('; ');
  }
  return `Request failed (HTTP ${status})`;
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      method,
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(`Cannot reach the server at ${API_URL}`, 0);
  }
  if (!res.ok) {
    const data: unknown = await res.json().catch(() => null);
    throw new ApiError(detailMessage(data, res.status), res.status);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

const enc = encodeURIComponent;

// Collections
export const listCollections = () => request<Collection[]>('GET', '/collections');
export const syncCollection = (collectionId: string) =>
  request<SyncLog>('POST', `/sync?collection=${enc(collectionId)}`);
export const getLatestSyncLog = (collectionId: string) =>
  request<SyncLog>('GET', `/collections/${enc(collectionId)}/sync-log`);

// Sources
export const listSources = (collectionId: string, includeArchived = false) =>
  request<SourceSummary[]>(
    'GET',
    `/collections/${enc(collectionId)}/sources${includeArchived ? '?include_archived=true' : ''}`,
  );
export const getSource = (sourceId: number) => request<SourceDetail>('GET', `/sources/${sourceId}`);

// Ask
export const ask = (collectionId: string, body: AskRequest) =>
  request<AskResponse>('POST', `/collections/${enc(collectionId)}/ask`, body);

// Question banks
export const listQuestionBanks = (collectionId: string) =>
  request<QuestionBank[]>('GET', `/collections/${enc(collectionId)}/question-banks`);
export const createQuestionBank = (collectionId: string, body: QuestionBankCreate) =>
  request<QuestionBank>('POST', `/collections/${enc(collectionId)}/question-banks`, body);
export const deleteQuestionBank = (bankId: number) => request<void>('DELETE', `/question-banks/${bankId}`);
export const runQuestionBank = (bankId: number, filters?: AskFilters) =>
  request<BankRun>('POST', `/question-banks/${bankId}/run`, filters ? { filters } : undefined);
export const getBankRun = (runId: number) => request<BankRun>('GET', `/bank-runs/${runId}`);
/** Plain link target for the Markdown download (not fetched by the app). */
export const bankRunReportUrl = (runId: number) => `${API_URL}/bank-runs/${runId}/report.md`;

// Notes
export const listNotes = (collection?: string) =>
  request<Note[]>('GET', `/notes${collection ? `?collection=${enc(collection)}` : ''}`);
export const createNote = (body: NoteCreate) => request<Note>('POST', '/notes', body);
export const deleteNote = (noteId: number) => request<void>('DELETE', `/notes/${noteId}`);
