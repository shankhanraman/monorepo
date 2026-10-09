const API_URL = "/api"; // same origin: Vite proxies /api to FastAPI (ingress does it in production)

type FastApiError = { detail?: string | { loc: (string | number)[]; msg: string }[] };

/**
 * Call FastAPI. The HttpOnly session cookie is sent automatically (same origin); there is no Authorization header.
 * Writes add X-CSRF: 1, which the backend requires so other sites can't make the browser write with its cookie.
 * Throws an Error with FastAPI's message on non-2xx. Resolves to undefined for 204 No Content.
 */
export async function apiFetch<T>(path: string, init: { method?: string; body?: unknown } = {}): Promise<T> {
  const method = init.method ?? "GET";
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (method !== "GET") headers["X-CSRF"] = "1";
  const res = await fetch(API_URL + path, {
    method,
    headers,
    body: init.body === undefined ? undefined : JSON.stringify(init.body),
  });
  if (!res.ok) {
    const { detail } = (await res.json().catch(() => ({}))) as FastApiError;
    const message = Array.isArray(detail) ? detail.map((d) => `${d.loc.at(-1)}: ${d.msg}`).join(", ") : detail;
    throw new Error(message ?? `${res.status} ${res.statusText}`);
  }
  return (res.status === 204 ? undefined : await res.json()) as T;
}
