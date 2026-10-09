import { keycloak } from "./keycloak";
import "./SignInMenu.css";

/**
 * Guest: "Sign in" menu with Log in / Register. Signed in: name + Log out.
 * All three are full-page redirects to Keycloak and back, so reading keycloak.authenticated at render is enough.
 * Log in: Kerberos users with a ticket (kinit) get in without a password; everyone else sees the password form.
 * Register: Keycloak's sign-up form; the new account is a Keycloak password user (not a Kerberos principal).
 */
export default function SignInMenu() {
  if (keycloak.authenticated) {
    return (
      <div className="signin">
        <span>
          Signed in as <strong>{keycloak.tokenParsed?.preferred_username}</strong>
        </span>
        <button onClick={() => keycloak.logout({ redirectUri: window.location.origin })}>Log out</button>
      </div>
    );
  }

  return (
    <details className="signin-menu">
      <summary>Sign in</summary>
      <div className="signin-menu-items">
        <button onClick={() => keycloak.login()}>Log in</button>
        <button onClick={() => keycloak.register()}>Register</button>
      </div>
    </details>
  );
}
