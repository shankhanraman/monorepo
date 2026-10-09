import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { keycloak } from "./auth/keycloak";

const root = createRoot(document.getElementById("root")!);

// Run once before React renders (StrictMode runs effects twice).
// check-sso: picks up an existing Keycloak session but never forces a login, so guests can browse.
// checkLoginIframe off: the session-check iframe needs Keycloak's cookies inside the app's page. That happens to
// work here (localhost:8081 and localhost:5174 are the same site), but in production Keycloak has its own domain,
// browsers block those third-party cookies, and the iframe would always say "logged out". The redirect works everywhere.
keycloak
  .init({ onLoad: "check-sso", pkceMethod: "S256", checkLoginIframe: false })
  .then(() =>
    root.render(
      <StrictMode>
        <App />
      </StrictMode>,
    ),
  )
  .catch(() => root.render(<p>Could not reach Keycloak at {keycloak.authServerUrl}. Is docker compose up?</p>));
