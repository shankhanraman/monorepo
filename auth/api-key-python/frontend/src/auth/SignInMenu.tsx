import { useState } from "react";
import { clearApiKey, getApiKey, setApiKey } from "./apiKey";
import "./SignInMenu.css";

/**
 * Guest: a field to paste an API key. Signed in: shows the key's prefix + Forget.
 * Saving/forgetting reloads the page, so reading getApiKey() at render is enough.
 */
export default function SignInMenu() {
  const key = getApiKey();
  const [draft, setDraft] = useState("");

  if (key) {
    return (
      <div className="signin">
        <span>
          Using key <strong>{key.slice(0, 9)}…</strong>
        </span>
        <button onClick={() => { clearApiKey(); location.reload(); }}>Forget key</button>
      </div>
    );
  }

  return (
    <details className="signin-menu">
      <summary>Use API key</summary>
      <form
        className="signin-menu-items"
        onSubmit={(e) => {
          e.preventDefault();
          if (draft.trim()) { setApiKey(draft); location.reload(); }
        }}
      >
        <input value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="X-API-Key value" />
        <button type="submit">Use key</button>
      </form>
    </details>
  );
}
