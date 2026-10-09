import { useState, type FormEvent } from "react";
import type { UserCreate } from "./types";

type Props = {
  /** Present = edit mode (prefilled, not cleared after save). Absent = create mode. */
  initial?: UserCreate;
  submitLabel: string;
  onSubmit: (data: UserCreate) => Promise<void>;
  onCancel?: () => void;
};

export default function UserForm({ initial, submitLabel, onSubmit, onCancel }: Props) {
  const [form, setForm] = useState<UserCreate>(initial ?? { username: "", email: "" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await onSubmit(form);
      if (!initial) setForm({ username: "", email: "" });
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="user-form" onSubmit={submit}>
      <label>
        Username
        <input required value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} />
      </label>
      <label>
        Email
        <input
          type="email"
          required
          value={form.email}
          onChange={(e) => setForm({ ...form, email: e.target.value })}
        />
      </label>
      <button type="submit" disabled={busy}>
        {busy ? "Saving…" : submitLabel}
      </button>
      {onCancel && (
        <button type="button" onClick={onCancel}>
          Cancel
        </button>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </form>
  );
}
