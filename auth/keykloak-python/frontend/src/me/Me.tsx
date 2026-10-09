import { useEffect, useState } from "react";
import { apiFetch } from "../auth/apiFetch";

type MeResponse = { username: string | null; email: string | null };

/** Asks FastAPI who we are: proves the Kerberos → Keycloak → JWT → FastAPI chain works. */
export default function Me() {
  const [me, setMe] = useState<MeResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<MeResponse>("/me").then(setMe, (e: Error) => setError(e.message));
  }, []);

  if (error) return <p className="error">FastAPI rejected the token: {error}</p>;
  if (!me) return <p>Checking token with FastAPI…</p>;
  return (
    <p>
      FastAPI says you are <strong>{me.username}</strong>
      {me.email && ` (${me.email})`}
    </p>
  );
}
