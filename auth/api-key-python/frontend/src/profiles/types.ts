// Mirrors fastapi-seerver/app/models/profiles.py
export type Profile = { id: number; user_id: number; bio: string };
export type ProfileCreate = Omit<Profile, "id">;
