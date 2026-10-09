import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// The browser only ever talks to this origin (http://localhost:5175). /api and /auth are forwarded to FastAPI,
// so the session cookie is first-party and no CORS is needed. In production, ingress path routing does the same.
const backend = "http://localhost:8002";

export default defineConfig({
  plugins: [react()],
  // Must match the redirect URI of the "bff" client in keycloak/bff-lab-realm.json (http://localhost:5175/auth/callback)
  server: {
    port: 5175,
    strictPort: true,
    proxy: { "/api": backend, "/auth": backend },
  },
  // Don't wipe the terminal on start: setup-local-dev.ps1 runs FastAPI's logs in the same terminal
  clearScreen: false,
  test: { environment: "jsdom", globals: true },
});
