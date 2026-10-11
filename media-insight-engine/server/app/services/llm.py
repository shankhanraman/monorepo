"""The one place that calls Claude: model, effort, structured output, refusal fallback, timing."""
import os
import time
from string import Template

import anthropic

from app.config import settings

FALLBACK_BETA = "server-side-fallback-2026-07-01"
_client: anthropic.Anthropic | None = None


class ModelRefusal(Exception):
    pass


class ModelUnavailable(Exception):
    pass


def client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
            raise ModelUnavailable("ANTHROPIC_API_KEY is not set: add it to .env and restart the server")
        _client = anthropic.Anthropic(max_retries=3)
    return _client


def api_error_message(e: anthropic.APIStatusError) -> str:
    """Claude's own reason (e.g. 'Your credit balance is too low…') instead of the raw exception dump."""
    body = e.body if isinstance(e.body, dict) else {}
    reason = (body.get("error") or {}).get("message") if isinstance(body.get("error"), dict) else None
    return f"Claude API error: {reason or e.message}"


def prompt(name: str, **values) -> str:
    """Prompts are plain files (PRD), re-read on every call so edits apply without a restart."""
    return Template((settings.prompts_dir / f"{name}.md").read_text(encoding="utf-8")).safe_substitute(values)


def parse(model: str, effort: str, system: str, user: str, schema, max_tokens: int = 16000):
    """Structured output → (parsed pydantic object, model that served it, latency ms)."""
    t0 = time.monotonic()
    resp = client().beta.messages.parse(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
        output_format=schema,
        output_config={"effort": effort},
        betas=[FALLBACK_BETA],
        fallbacks="default",  # server-side fallback when a safety classifier declines
    )
    if resp.stop_reason == "refusal":
        details = getattr(resp, "stop_details", None)
        raise ModelRefusal(getattr(details, "explanation", None) or "The model declined this request")
    if resp.stop_reason == "max_tokens":
        raise RuntimeError("Model output was cut off (max_tokens)")
    return resp.parsed_output, resp.model, int((time.monotonic() - t0) * 1000)
