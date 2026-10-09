import { goTo, session } from "./session";
import "./SignInMenu.css";

/**
 * Guest: "Sign in" menu with Log in / Register. Signed in: name + Log out.
 * Log in / Register navigate to the backend (/auth/login, /auth/register), which runs the OAuth 2.0 flow with
 * Keycloak and comes back with an HttpOnly session cookie. The SPA never sees a token.
 */
export default function SignInMenu() {
  if (session.user) {
    return (
      <div className="signin">
        <span>
          Signed in as <strong>{session.user.username}</strong>
        </span>
        <button onClick={logout}>Log out</button>
      </div>
    );
  }

  return (
    <details className="signin-menu">
      <summary>Sign in</summary>
      <div className="signin-menu-items">
        <button onClick={() => goTo("/auth/login")}>Log in</button>
        <button onClick={() => goTo("/auth/register")}>Register</button>
      </div>
    </details>
  );
}

async function logout() {
  // The backend deletes the session, ends the Keycloak session server-to-server and clears the cookie.
  await fetch("/auth/logout", { method: "POST", headers: { "X-CSRF": "1" } });
  goTo("/");
}
