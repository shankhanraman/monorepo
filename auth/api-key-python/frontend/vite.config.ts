import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  // Don't wipe the terminal on start: setup-local-dev.ps1 runs FastAPI's logs in the same terminal
  clearScreen: false,
  // Must match the redirect URI / web origin of the "frontend" client in keycloak/jwt-lab-realm.json
  server: { port: 5174, strictPort: true },
  test: { environment: "jsdom", globals: true },
});
