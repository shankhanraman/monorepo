import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "../auth/apiFetch";
import type { User } from "../users/types";
import ProfileForm from "./ProfileForm";
import type { Profile, ProfileCreate } from "./types";
import "./Profiles.css";

type Props = {
  /** Signed in: show create / edit / delete. Guests only read (public API). */
  canEdit: boolean;
  /** Bumped when users change (rename, delete cascades to profiles), triggers a reload. */
  version: number;
};

export default function Profiles({ canEdit, version }: Props) {
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);

  const load = useCallback(() => {
    Promise.all([apiFetch<Profile[]>("/profiles/"), apiFetch<User[]>("/users/")]).then(
      ([p, u]) => {
        setProfiles(p);
        setUsers(u);
      },
      (e: Error) => setError(e.message),
    );
  }, []);

  useEffect(load, [load, version]);

  const owner = (id: number) => users.find((u) => u.id === id)?.username ?? `user ${id}`;

  async function create(data: ProfileCreate) {
    await apiFetch<Profile>("/profiles/", { method: "POST", body: data });
    load();
  }

  async function save(id: number, data: ProfileCreate) {
    await apiFetch<Profile>(`/profiles/${id}`, { method: "PUT", body: data });
    setEditingId(null);
    load();
  }

  async function remove(profile: Profile) {
    if (!confirm(`Delete this profile of ${owner(profile.user_id)}?`)) return;
    try {
      await apiFetch<void>(`/profiles/${profile.id}`, { method: "DELETE" });
      load();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <section className="profiles">
      <h2>Profiles</h2>
      {canEdit &&
        (users.length === 0 ? (
          <p className="muted">Create a user first, then add profiles for them.</p>
        ) : (
          <ProfileForm users={users} submitLabel="Add profile" onSubmit={create} />
        ))}
      {error && <p className="error">{error}</p>}
      {profiles.length === 0 ? (
        <p>No profiles yet.</p>
      ) : (
        <ul className="profiles-list">
          {profiles.map((p) =>
            editingId === p.id ? (
              <li key={p.id}>
                <ProfileForm
                  users={users}
                  initial={{ user_id: p.user_id, bio: p.bio }}
                  submitLabel="Save"
                  onSubmit={(data) => save(p.id, data)}
                  onCancel={() => setEditingId(null)}
                />
              </li>
            ) : (
              <li key={p.id}>
                <strong>{owner(p.user_id)}</strong> <span className="muted">{p.bio || "(no bio)"}</span>
                {canEdit && (
                  <span className="row-actions">
                    <button onClick={() => setEditingId(p.id)}>Edit</button>
                    <button onClick={() => remove(p)}>Delete</button>
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
