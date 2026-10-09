import { useState, type FormEvent } from "react";
import type { User } from "../users/types";
import type { ProfileCreate } from "./types";

type Props = {
  users: User[];
  /** Present = edit mode (prefilled, not cleared after save). Absent = create mode. */
  initial?: ProfileCreate;
  submitLabel: string;
  onSubmit: (data: ProfileCreate) => Promise<void>;
  onCancel?: () => void;
};

export default function ProfileForm({ users, initial, submitLabel, onSubmit, onCancel }: Props) {
  const empty = { user_id: users[0]?.id ?? 0, bio: "" };
  const [form, setForm] = useState<ProfileCreate>(initial ?? empty);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // The owner list can change (user created/deleted elsewhere): fall back to the first user if ours is gone,
  // and submit exactly what the <select> shows.
  const userId = users.some((u) => u.id === form.user_id) ? form.user_id : (users[0]?.id ?? 0);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await onSubmit({ ...form, user_id: userId });
      if (!initial) setForm(empty);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="profile-form" onSubmit={submit}>
      <label>
        User
        <select required value={userId} onChange={(e) => setForm({ ...form, user_id: Number(e.target.value) })}>
          {users.map((u) => (
            <option key={u.id} value={u.id}>
              {u.username}
            </option>
          ))}
        </select>
      </label>
      <label className="profile-bio">
        Bio
        <textarea rows={2} value={form.bio} onChange={(e) => setForm({ ...form, bio: e.target.value })} />
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
