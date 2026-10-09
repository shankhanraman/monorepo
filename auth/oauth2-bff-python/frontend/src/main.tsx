import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { loadSession } from "./auth/session";

const root = createRoot(document.getElementById("root")!);

// Ask the backend who is signed in (via the HttpOnly session cookie) once, before React renders.
// Guests get 401, which simply means "not signed in".
loadSession()
  .then(() =>
    root.render(
      <StrictMode>
        <App />
      </StrictMode>,
    ),
  )
  .catch(() => root.render(<p>Could not reach the backend at /api. Is FastAPI running on :8002?</p>));
