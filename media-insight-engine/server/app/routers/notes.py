from fastapi import APIRouter, HTTPException
from psycopg.types.json import Jsonb

from app.db import pool
from app.models.api import Note, NoteCreate

router = APIRouter(tags=["notes"])


@router.get("/notes", response_model=list[Note])
def list_notes(collection: str | None = None):
    with pool().connection() as conn:
        return conn.execute("SELECT * FROM notes WHERE %(c)s::text IS NULL OR collection_id = %(c)s ORDER BY id DESC",
                            {"c": collection}).fetchall()


@router.post("/notes", response_model=Note, status_code=201)
def create_note(body: NoteCreate):
    with pool().connection() as conn:
        return conn.execute(
            """INSERT INTO notes (collection_id, question, answer_md, coverage, citations, comment)
               VALUES (%s, %s, %s, %s, %s, %s) RETURNING *""",
            (body.collection_id, body.question, body.answer_md, body.coverage,
             Jsonb([c.model_dump(mode="json") for c in body.citations]), body.comment)).fetchone()


@router.delete("/notes/{note_id}", status_code=204)
def delete_note(note_id: int):
    with pool().connection() as conn:
        if not conn.execute("DELETE FROM notes WHERE id = %s RETURNING id", (note_id,)).fetchone():
            raise HTTPException(404, "Not found")
