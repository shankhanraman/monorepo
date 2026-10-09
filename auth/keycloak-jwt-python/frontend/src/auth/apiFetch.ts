import { keycloak } from "./keycloak";

const API_URL = "http://localhost:8001";

type FastApiError = { detail?: string | { loc: (string | number)[]; msg: string }[] };

/**
 * Call FastAPI. Sends the Keycloak token when signed in (guests can still use the public reads).
 * Throws an Error with FastAPI's message on non-2xx. Resolves to undefined for 204 No Content.
 */
export async function apiFetch<T>(path: string, init: { method?: string; body?: unknown } = {}): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (keycloak.authenticated) {
    await keycloak.updateToken(30); // refresh if it expires within 30s
    headers.Authorization = `Bearer ${keycloak.token}`;
  }
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
