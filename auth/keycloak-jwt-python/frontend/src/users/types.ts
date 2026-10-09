// Mirrors fastapi-seerver/app/models/users.py
export type User = { id: number; username: string; email: string };
export type UserCreate = Omit<User, "id">;
