import { getApiKey } from "./apiKey";

const API_URL = "http://localhost:8004";

type FastApiError = { detail?: string | { loc: (string | number)[]; msg: string }[] };

/**
 * Call FastAPI. Sends the API key in the X-API-Key header when one is stored
 * (guests can still use the public reads). Throws FastAPI's message on non-2xx.
 */
export async function apiFetch<T>(path: string, init: { method?: string; body?: unknown } = {}): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const key = getApiKey();
  if (key) headers["X-API-Key"] = key;
  const res = await fetch(API_URL + path, {
    method: init.method ?? "GET",
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
