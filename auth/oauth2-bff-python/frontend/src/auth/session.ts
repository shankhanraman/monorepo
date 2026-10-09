export type SessionUser = { username: string; email: string | null };

/**
 * Who is signed in. Set once by loadSession() before React renders. Login, register and logout are full-page
 * navigations through the backend, so it can't change while the page is open.
 * There is no token here (or anywhere in JS): the backend keeps it and the browser holds an HttpOnly cookie.
 */
export const session: { user: SessionUser | null } = { user: null };

export async function loadSession(): Promise<void> {
  const res = await fetch("/api/me"); // same origin: the HttpOnly session cookie goes along automatically
  if (res.status === 401) session.user = null; // guest
  else if (res.ok) session.user = (await res.json()) as SessionUser;
  else throw new Error(`GET /api/me failed: ${res.status}`);
}

/** Full-page navigation (to /auth/login, /auth/register, or home after logout). Separate so tests can mock it. */
export function goTo(url: string): void {
  window.location.assign(url);
}
