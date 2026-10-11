"""Question banks: save, run in the background, report, Markdown export (FR-5)."""
import html
import logging

import anthropic
from psycopg import errors
from psycopg.types.json import Jsonb

from app.db import pool
from app.services import answers, jobs, llm

log = logging.getLogger("banks")


class RunBusy(Exception):
    pass


def start_run(bank_id: int, filters: dict) -> int:
    """Raises LookupError (no bank) or RunBusy (already running)."""
    with pool().connection() as conn:
        bank = conn.execute("SELECT * FROM question_banks WHERE id = %s", (bank_id,)).fetchone()
        if not bank:
            raise LookupError(bank_id)
        try:
            with conn.transaction():
                run_id = conn.execute(
                    "INSERT INTO bank_runs (bank_id, total, filters) VALUES (%s, %s, %s) RETURNING id",
                    (bank_id, len(bank["questions"]), Jsonb(filters))).fetchone()["id"]
                item_ids = [conn.execute(
                    """INSERT INTO answers (collection_id, run_id, item_index, question, status)
                       VALUES (%s, %s, %s, %s, 'pending') RETURNING id""",
                    (bank["collection_id"], run_id, i, q)).fetchone()["id"] for i, q in enumerate(bank["questions"])]
        except errors.UniqueViolation:
            running = conn.execute("SELECT id FROM bank_runs WHERE bank_id = %s AND status = 'running'",
                                   (bank_id,)).fetchone()
            raise RunBusy(f"Bank {bank_id} is already running (run {running['id'] if running else '?'})")
    for item_id in item_ids:
        jobs.submit_bank_item(item_id)
    return run_id


def run_item(answer_id: int) -> None:
    """One bank question through the same Q&A graph as the chat (FR-5.2)."""
    with pool().connection() as conn:
        item = conn.execute(
            """SELECT a.id, a.question, a.collection_id, r.filters, r.id AS run_id
               FROM answers a JOIN bank_runs r ON r.id = a.run_id WHERE a.id = %s""", (answer_id,)).fetchone()
    try:
        answers.save(item["collection_id"], answers.ask(item["collection_id"], item["question"], [], item["filters"]),
                     answer_id)
    except Exception as e:
        log.exception("bank item %s failed", answer_id)
        if isinstance(e, anthropic.APIStatusError):
            reason = llm.api_error_message(e)
        elif isinstance(e, (llm.ModelUnavailable, llm.ModelRefusal)):
            reason = str(e)
        else:
            reason = f"{type(e).__name__}: {e}"
        with pool().connection() as conn:
            conn.execute("UPDATE answers SET status = 'failed', error = %s WHERE id = %s", (reason[:500], answer_id))
    with pool().connection() as conn:
        conn.execute(
            """UPDATE bank_runs SET done = done + 1,
                 status = CASE WHEN done + 1 >= total THEN 'done' ELSE status END,
                 finished_at = CASE WHEN done + 1 >= total THEN now() ELSE finished_at END
               WHERE id = %s""", (item["run_id"],))


def get_run(run_id: int) -> dict | None:
    with pool().connection() as conn:
        run = conn.execute(
            """SELECT r.id, r.bank_id, b.name AS bank_name, b.collection_id, r.status, r.done, r.total,
                      r.created_at, r.finished_at
               FROM bank_runs r JOIN question_banks b ON b.id = r.bank_id WHERE r.id = %s""", (run_id,)).fetchone()
        if not run:
            return None
        rows = conn.execute("SELECT * FROM answers WHERE run_id = %s ORDER BY item_index", (run_id,)).fetchall()
    run["items"] = [{
        "index": a["item_index"], "question": a["question"], "status": a["status"],
        "answer_md": a["answer_md"] if a["status"] == "done" else None,
        "coverage": a["coverage"] if a["status"] == "done" else None,
        "watch": a["watch"] if a["status"] == "done" else [],
        "stale_warning": a["stale_warning"], "error": a["error"],
    } for a in rows]
    return run


def report_markdown(run: dict) -> str:
    """FR-5.4: every question with answer, coverage and timestamp links."""
    when = run["created_at"].date().isoformat()
    out = [f"# {run['bank_name']}",
           f"_{run['collection_id']} · run {run['id']} · {when} · summary of sources; "
           f"verify policies on the official admissions site_", ""]
    for item in run["items"]:
        out.append(f"## {item['index'] + 1}. {item['question']}")
        if item["status"] != "done":
            out += [f"_{item['status']}{': ' + item['error'] if item['error'] else ''}_", ""]
            continue
        out += [f"**Coverage:** {item['coverage']}", "", item["answer_md"], ""]
        if item["stale_warning"]:
            out += [f"> ⚠ {item['stale_warning']}", ""]
        if item["watch"]:
            out.append("**Watch these**")
            for n, c in enumerate(item["watch"], start=1):
                date = c["published_at"] or "date unknown"
                out.append(f"{n}. [{c['n']}] [{c['source_title']} — {c['label']}]({c['deep_link']}) ({date})")
            out.append("")
    return "\n".join(out).rstrip() + "\n"


COVERAGE_COLOR = {"strong": "#1a7f37", "partial": "#9a6700", "none": "#6e7781"}


def report_html(run: dict) -> str:
    """The same report as the Markdown, as a printable HTML page (everything escaped)."""
    e = html.escape
    when = run["created_at"].date().isoformat()
    items = []
    for item in run["items"]:
        head = f"<h2>{item['index'] + 1}. {e(item['question'])}</h2>"
        if item["status"] != "done":
            items.append(f"<section>{head}<p class='muted'>{e(item['status'])}"
                         f"{': ' + e(item['error']) if item['error'] else ''}</p></section>")
            continue
        cov = item["coverage"] or "none"
        paras = "".join(f"<p>{e(p)}</p>" for p in (item["answer_md"] or "").split("\n\n") if p.strip())
        stale = f"<p class='warn'>⚠ {e(item['stale_warning'])}</p>" if item["stale_warning"] else ""
        watch = "".join(
            f"<li>[{c['n']}] <a href='{e(c['deep_link'])}'>{e(c['source_title'])} — {e(c['label'])}</a> "
            f"<span class='muted'>({e(c['published_at'] or 'date unknown')}){' ⚠' if c['stale'] else ''}</span></li>"
            for c in item["watch"])
        items.append(f"<section>{head}<p><span class='badge' style='background:{COVERAGE_COLOR[cov]}'>"
                     f"{e(cov)}</span></p>{paras}{stale}"
                     + (f"<h3>Watch these</h3><ol>{watch}</ol>" if watch else "") + "</section>")
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>{e(run['bank_name'])}</title><style>
body {{ font: 11pt/1.45 -apple-system, "Segoe UI", Roboto, Arial, sans-serif; color: #1f2328; }}
h1 {{ font-size: 18pt; margin: 0 0 4px; }} h2 {{ font-size: 13pt; margin: 18px 0 6px; }} h3 {{ font-size: 11pt; }}
section {{ break-inside: avoid; border-top: 1px solid #d0d7de; }}
.muted {{ color: #6e7781; }} .warn {{ color: #9a6700; }} a {{ color: #0969da; }}
.badge {{ color: #fff; border-radius: 10px; padding: 1px 8px; font-size: 9pt; }}
</style></head><body>
<h1>{e(run['bank_name'])}</h1>
<p class="muted">{e(run['collection_id'])} · run {run['id']} · {when} · summary of sources; verify policies on the official admissions site</p>
{''.join(items)}
</body></html>"""


def report_pdf(run: dict) -> bytes:
    """Printed with the Chromium that Crawl4AI already installed (no extra dependency)."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page()
            page.set_content(report_html(run), wait_until="load")
            return page.pdf(format="A4", margin={"top": "18mm", "bottom": "18mm", "left": "16mm", "right": "16mm"},
                            print_background=True)
        finally:
            browser.close()
