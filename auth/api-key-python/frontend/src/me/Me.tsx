import { useEffect, useState } from "react";
import { apiFetch } from "../auth/apiFetch";

type MeResponse = { name: string; prefix: string };

/** Asks FastAPI which key it accepted: proves the X-API-Key → FastAPI check works. */
export default function Me() {
  const [me, setMe] = useState<MeResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<MeResponse>("/me").then(setMe, (e: Error) => setError(e.message));
  }, []);

  if (error) return <p className="error">FastAPI rejected the key: {error}</p>;
  if (!me) return <p>Checking key with FastAPI…</p>;
  return (
    <p>
      FastAPI accepted key <strong>{me.name}</strong> ({me.prefix}…)
    </p>
  );
}
