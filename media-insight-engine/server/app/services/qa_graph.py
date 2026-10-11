"""Grounded Q&A as a small LangGraph graph (FR-4; see docs/dataflow.md §4).

retrieve → answer ─(strong/partial, or already retried)→ finalize
                  └(none, first try)→ rewrite_query → retrieve
"""
import re
from datetime import date
from typing import Callable, Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel

from app.config import settings
from app.services import llm
from app.services.links import app_link, deep_link, position_label, snippet

NOT_COVERED = "Not covered in your sources."


class AnswerDraft(BaseModel):
    coverage: Literal["strong", "partial", "none"]
    answer_md: str
    conflicts: str | None


class Rewrite(BaseModel):
    query: str


class QAState(TypedDict, total=False):
    collection: str
    college_name: str | None
    lens_text: str
    stale_months: int
    question: str
    history: list[dict]
    filters: dict
    query: str
    attempt: int
    hits: list[dict]
    draft: AnswerDraft
    model: str | None
    result: dict


# ---------- model calls (replaced by fakes in tests) ----------

def _excerpts(hits: list[dict]) -> str:
    out = []
    for n, h in enumerate(hits, start=1):
        where = position_label(h["type"], h["start_s"], h["end_s"], h["anchor"])
        out.append(f'[{n}] "{h["source_title"]}" ({h["host"] or "unknown"}, published '
                   f'{h["published_at"] or "date unknown"}) {where}\n<excerpt>\n{h["text"]}\n</excerpt>')
    return "\n\n".join(out)


def _history(history: list[dict]) -> str:
    if not history:
        return ""
    turns = "\n\n".join(f"Q: {t['question']}\nA: {t['answer_md']}" for t in history[-10:])
    return f"<earlier_conversation>\n{turns}\n</earlier_conversation>\n\n"


def llm_answer(state: QAState) -> tuple[AnswerDraft, str]:
    user = (_history(state.get("history", [])) + f"<excerpts>\n{_excerpts(state['hits'])}\n</excerpts>\n\n"
            f"Question: {state['question']}")
    draft, model, _ = llm.parse(settings.answer_model, "low", llm.prompt("answer", lens=state["lens_text"]),
                                user, AnswerDraft, max_tokens=8000)
    return draft, model


def llm_rewrite(state: QAState) -> str:
    user = _history(state.get("history", [])) + f"Question: {state['question']}"
    out, _, _ = llm.parse(settings.answer_model, "low", llm.prompt("rewrite", lens=state["lens_text"]),
                          user, Rewrite, max_tokens=2000)
    return out.query


# ---------- finalize: plain code, the grounding guarantee ----------

def is_stale(published: date | None, today: date, months: int) -> bool:
    if published is None:
        return True
    return (today.year - published.year) * 12 + (today.month - published.month) - (today.day < published.day) >= months


def citation(n: int, h: dict, stale: bool) -> dict:
    return {
        "n": n, "segment_id": h["segment_id"], "source_id": h["source_id"], "collection_id": h["collection_id"],
        "source_type": h["type"], "source_title": h["source_title"], "host": h["host"],
        "published_at": h["published_at"].isoformat() if h["published_at"] else None,
        "start_s": h["start_s"], "end_s": h["end_s"], "anchor": h["anchor"],
        "label": position_label(h["type"], h["start_s"], h["end_s"], h["anchor"]),
        "snippet": snippet(h["text"]),
        "deep_link": deep_link({"type": h["type"], "ext_id": h["ext_id"], "url": h["url"]}, h["start_s"], h["text"]),
        "app_link": app_link({"type": h["type"], "id": h["source_id"]}, h["start_s"], h["segment_id"]),
        "stale": stale,
    }


def finalize(question: str, draft: AnswerDraft | None, hits: list[dict], today: date, stale_months: int,
             college_name: str | None, retried: bool) -> dict:
    """Keep only [n] that point at retrieved segments, renumber, link, flag staleness, or say 'not covered'."""
    stale = [is_stale(h["published_at"], today, stale_months) for h in hits]
    text = draft.answer_md if draft else ""
    order: list[int] = []  # retrieved indexes in order of first citation
    for m in re.finditer(r"\[(\d+)\]", text):
        i = int(m.group(1)) - 1
        if 0 <= i < len(hits) and i not in order:
            order.append(i)
    base = {"question": question, "label": "Summary of sources", "conflicts": None, "retried": retried,
            "citations": [], "closest": [], "stale_warning": None, "watch": []}
    if not draft or draft.coverage == "none" or not order or not text.strip():
        return {**base, "answer_md": NOT_COVERED, "coverage": "none", "not_covered": True,
                "closest": [citation(n, h, s) for n, (h, s) in enumerate(zip(hits[:3], stale[:3]), start=1)]}
    new_n = {i: n for n, i in enumerate(order, start=1)}

    def renumber(s: str) -> str:
        s = re.sub(r"\[(\d+)\]", lambda m: f"[{new_n[int(m.group(1)) - 1]}]" if int(m.group(1)) - 1 in new_n else "", s)
        s = re.sub(r"[ \t]+([.,;:!?])", r"\1", s)        # space left before punctuation by a removed marker
        return re.sub(r"[ \t]{2,}", " ", s).strip()

    answer = renumber(text)
    cites = [citation(new_n[i], hits[i], stale[i]) for i in order]
    conflicts = renumber(draft.conflicts) if draft.conflicts else None
    old = [c for c in cites if c["stale"] and c["published_at"]]
    unknown = [c for c in cites if c["stale"] and not c["published_at"]]
    warning = None
    if old or unknown:
        parts = []
        if old:
            dates = ", ".join(sorted({c["published_at"] for c in old}))
            parts.append(f"Cited source{'s' if len(old) > 1 else ''} from {dates} "
                         f"{'are' if len(old) > 1 else 'is'} older than {stale_months} months.")
        if unknown:
            parts.append(f"{len(unknown)} cited source{'s have' if len(unknown) > 1 else ' has'} no publish date.")
        site = f"the official {college_name} admissions site" if college_name else "the official admissions site"
        warning = " ".join(parts) + f" Admissions policies change every year: verify on {site}."
    watch = sorted(cites, key=lambda c: order[c["n"] - 1])[:5]  # ranked by retrieval relevance
    return {**base, "answer_md": answer, "coverage": draft.coverage, "not_covered": False, "citations": cites,
            "stale_warning": warning, "conflicts": conflicts, "watch": watch}


# ---------- graph ----------

def build_graph(retrieve_fn: Callable, answer_fn: Callable = llm_answer, rewrite_fn: Callable = llm_rewrite,
                today_fn: Callable[[], date] = date.today):
    def retrieve(state: QAState):
        return {"hits": retrieve_fn(state["collection"], state["query"], state.get("filters") or {})}

    def answer(state: QAState):
        if not state["hits"]:
            return {"draft": AnswerDraft(coverage="none", answer_md="", conflicts=None)}
        draft, model = answer_fn(state)
        return {"draft": draft, "model": model}

    def route(state: QAState) -> str:
        return "rewrite_query" if state["draft"].coverage == "none" and state.get("attempt", 0) == 0 else "finalize"

    def rewrite_query(state: QAState):
        return {"query": rewrite_fn(state), "attempt": 1}

    def final(state: QAState):
        return {"result": finalize(state["question"], state.get("draft"), state.get("hits", []), today_fn(),
                                   state.get("stale_months", 18), state.get("college_name"),
                                   state.get("attempt", 0) > 0)}

    g = StateGraph(QAState)
    g.add_node("retrieve", retrieve)
    g.add_node("answer", answer)
    g.add_node("rewrite_query", rewrite_query)
    g.add_node("finalize", final)
    g.add_edge(START, "retrieve")
    g.add_edge("retrieve", "answer")
    g.add_conditional_edges("answer", route, ["rewrite_query", "finalize"])
    g.add_edge("rewrite_query", "retrieve")
    g.add_edge("finalize", END)
    return g.compile()


def search_query(question: str, history: list[dict]) -> str:
    """Follow-ups: search with the previous question too, so 'and how long should it be?' finds the topic."""
    return f"{history[-1]['question']} {question}" if history else question
