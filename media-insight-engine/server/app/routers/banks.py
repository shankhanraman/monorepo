from fastapi import APIRouter, HTTPException, Response

from app.config import ConfigError, load_collection
from app.db import pool
from app.models.api import BankRun, QuestionBank, QuestionBankCreate, RunRequest
from app.routers.collections import require_collection
from app.services import banks
from app.services.sync import upsert_collection

router = APIRouter(tags=["question-banks"])

BANK_COLUMNS = """b.id, b.collection_id, b.name, b.questions, b.created_at,
    (SELECT max(r.id) FROM bank_runs r WHERE r.bank_id = b.id) AS latest_run_id"""


@router.get("/collections/{collection_id}/question-banks", response_model=list[QuestionBank])
def list_banks(collection_id: str):
    require_collection(collection_id)
    with pool().connection() as conn:
        return conn.execute(f"SELECT {BANK_COLUMNS} FROM question_banks b WHERE b.collection_id = %s ORDER BY b.id DESC",
                            (collection_id,)).fetchall()


@router.post("/collections/{collection_id}/question-banks", response_model=QuestionBank, status_code=201)
def create_bank(collection_id: str, body: QuestionBankCreate):
    require_collection(collection_id)
    questions = list(dict.fromkeys(q.strip() for q in body.questions if q.strip()))
    if not questions or any(not 3 <= len(q) <= 2000 for q in questions):
        raise HTTPException(422, "Each question must be 3–2000 characters")
    with pool().connection() as conn:
        if not conn.execute("SELECT 1 FROM collections WHERE id = %s", (collection_id,)).fetchone():
            try:  # never synced: create the collection row from its file so the bank has a parent
                upsert_collection(conn, load_collection(collection_id), synced=False)
            except ConfigError as e:
                raise HTTPException(422, str(e))
        bank_id = conn.execute("INSERT INTO question_banks (collection_id, name, questions) VALUES (%s, %s, %s) RETURNING id",
                               (collection_id, body.name.strip(), questions)).fetchone()["id"]
        return conn.execute(f"SELECT {BANK_COLUMNS} FROM question_banks b WHERE b.id = %s", (bank_id,)).fetchone()


@router.delete("/question-banks/{bank_id}", status_code=204)
def delete_bank(bank_id: int):
    with pool().connection() as conn:
        if not conn.execute("DELETE FROM question_banks WHERE id = %s RETURNING id", (bank_id,)).fetchone():
            raise HTTPException(404, "Not found")


@router.post("/question-banks/{bank_id}/run", response_model=BankRun, status_code=202)
def run_bank(bank_id: int, body: RunRequest | None = None):
    try:
        run_id = banks.start_run(bank_id, (body or RunRequest()).filters.model_dump(mode="json"))
    except LookupError:
        raise HTTPException(404, "Not found")
    except banks.RunBusy as e:
        raise HTTPException(409, str(e))
    return banks.get_run(run_id)


@router.get("/bank-runs/{run_id}", response_model=BankRun)
def get_run(run_id: int):
    run = banks.get_run(run_id)
    if not run:
        raise HTTPException(404, "Not found")
    return run


@router.get("/bank-runs/{run_id}/report.md", response_class=Response,
            responses={200: {"content": {"text/markdown": {}}}})
def export_markdown(run_id: int):
    run = banks.get_run(run_id)
    if not run:
        raise HTTPException(404, "Not found")
    if run["status"] == "running":
        raise HTTPException(409, f"Run {run_id} is still running")
    filename = f"{run['collection_id']}-report-{run_id}.md"
    return Response(banks.report_markdown(run), media_type="text/markdown; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})
