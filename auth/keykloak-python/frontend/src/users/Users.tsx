import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "../auth/apiFetch";
import type { User, UserCreate } from "./types";
import UserForm from "./UserForm";
import "./Users.css";

type Props = {
  /** Signed in: show create / edit / delete. Guests only read (public API). */
  canEdit: boolean;
  /** Called after any change, so other features (profiles) can reload. */
  onChange: () => void;
};

export default function Users({ canEdit, onChange }: Props) {
  const [users, setUsers] = useState<User[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);

  const load = useCallback(() => {
    apiFetch<User[]>("/users/").then(setUsers, (e: Error) => setError(e.message));
  }, []);

  useEffect(load, [load]);

  function changed() {
    load();
    onChange();
  }

  async function create(data: UserCreate) {
    await apiFetch<User>("/users/", { method: "POST", body: data });
    changed();
  }

  async function save(id: number, data: UserCreate) {
    await apiFetch<User>(`/users/${id}`, { method: "PUT", body: data });
    setEditingId(null);
    changed();
  }

  async function remove(user: User) {
    if (!confirm(`Delete ${user.username} and all of their profiles?`)) return;
    try {
      await apiFetch<void>(`/users/${user.id}`, { method: "DELETE" });
      changed();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <section className="users">
      <h2>Users</h2>
      {canEdit && <UserForm submitLabel="Create user" onSubmit={create} />}
      {error && <p className="error">{error}</p>}
      {users.length === 0 ? (
        <p>No users yet.</p>
      ) : (
        <ul className="users-list">
          {users.map((u) =>
            editingId === u.id ? (
              <li key={u.id}>
                <UserForm
                  initial={{ username: u.username, email: u.email }}
                  submitLabel="Save"
                  onSubmit={(data) => save(u.id, data)}
                  onCancel={() => setEditingId(null)}
                />
              </li>
            ) : (
              <li key={u.id}>
                <strong>{u.username}</strong> <span className="muted">{u.email}</span>
                {canEdit && (
                  <span className="row-actions">
                    <button onClick={() => setEditingId(u.id)}>Edit</button>
                    <button onClick={() => remove(u)}>Delete</button>
                  </span>
                )}
              </li>
            ),
          )}
        </ul>
      )}
    </section>
  );
}
