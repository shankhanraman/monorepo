import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";

// No identity provider in this lab: the API key is read from localStorage by apiFetch.
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
