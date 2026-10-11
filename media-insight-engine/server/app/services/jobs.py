"""Background work inside the API process (PRD: one process, no queue). Status lives in the database."""
import logging
from concurrent.futures import ThreadPoolExecutor

from app.config import settings

log = logging.getLogger("jobs")
# ponytail: per-process pools; run a single server replica. A real queue is the upgrade path.
_ingest = ThreadPoolExecutor(settings.ingest_workers, thread_name_prefix="ingest")
_bank = ThreadPoolExecutor(settings.bank_workers, thread_name_prefix="bank")


def _safe(fn, *args):
    try:
        fn(*args)
    except Exception:  # the job functions record their own failures; this only guards the pool
        log.exception("background job %s%s crashed", fn.__name__, args)


def submit_ingest(source_id: int) -> None:
    from app.services.ingest import ingest_source
    _ingest.submit(_safe, ingest_source, source_id)


def submit_bank_item(answer_id: int) -> None:
    from app.services.banks import run_item
    _bank.submit(_safe, run_item, answer_id)


def recover() -> None:
    """At startup: re-queue sources a restart interrupted, and close bank runs that can't finish."""
    from app.db import pool
    with pool().connection() as conn:
        ids = [r["id"] for r in conn.execute(
            """UPDATE sources SET status = 'queued', updated_at = now()
               WHERE status IN ('queued', 'transcribing', 'analyzing') AND NOT archived RETURNING id""")]
        conn.execute(
            """UPDATE answers SET status = 'failed', error = 'Server restarted during the run'
               WHERE status = 'pending' AND run_id IS NOT NULL""")
        conn.execute(
            """UPDATE bank_runs SET status = 'failed', finished_at = now(),
                 done = (SELECT count(*) FROM answers a WHERE a.run_id = bank_runs.id)
               WHERE status = 'running'""")
    for source_id in ids:
        submit_ingest(source_id)
    if ids:
        log.info("re-queued %d interrupted sources", len(ids))
