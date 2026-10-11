"""Ask a question: run the Q&A graph and store the answer (FR-4)."""
import time

from psycopg.types.json import Jsonb

from app.config import ConfigError, collection_slugs, load_collection
from app.db import pool
from app.services import qa_graph, retrieve

_graph = None


def graph():
    global _graph
    if _graph is None:
        _graph = qa_graph.build_graph(retrieve.retrieve)
    return _graph


def lens_for(collection: str) -> tuple[str, int, str | None]:
    """(lens_text, stale_after_months, college name). Raises FileNotFoundError for unknown collections."""
    if collection != "all":
        col = load_collection(collection)
        return col.lens_text, col.lens.stale_after_months, col.name
    for slug in collection_slugs():  # all colleges share a lens in practice; use the first valid one
        try:
            col = load_collection(slug)
            return col.lens_text, col.lens.stale_after_months, None
        except (FileNotFoundError, ConfigError):
            continue
    raise FileNotFoundError("no valid collection files")


def ask(collection: str, question: str, history: list[dict] | None = None, filters: dict | None = None) -> dict:
    lens_text, stale_months, name = lens_for(collection)
    history = history or []
    t0 = time.monotonic()
    state = graph().invoke({
        "collection": collection, "college_name": name, "lens_text": lens_text, "stale_months": stale_months,
        "question": question, "history": history, "filters": filters or {},
        "query": qa_graph.search_query(question, history), "attempt": 0,
    })
    result = state["result"]
    result["model"] = state.get("model")
    result["latency_ms"] = int((time.monotonic() - t0) * 1000)
    return result


def save(collection: str, result: dict, answer_id: int | None = None) -> int:
    """Insert a chat answer, or fill in a pending bank item."""
    values = (result["answer_md"], result["coverage"], Jsonb(result["citations"]), Jsonb(result["closest"]),
              Jsonb(result["watch"]), result["stale_warning"], result["conflicts"], result["retried"],
              result.get("model"), result.get("latency_ms"))
    with pool().connection() as conn:
        if answer_id is None:
            return conn.execute(
                """INSERT INTO answers (collection_id, question, answer_md, coverage, citations, closest, watch,
                                        stale_warning, conflicts, retried, model, latency_ms)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                (collection, result["question"], *values)).fetchone()["id"]
        conn.execute(
            """UPDATE answers SET status = 'done', answer_md = %s, coverage = %s, citations = %s, closest = %s,
                 watch = %s, stale_warning = %s, conflicts = %s, retried = %s, model = %s, latency_ms = %s
               WHERE id = %s""", (*values, answer_id))
        return answer_id
