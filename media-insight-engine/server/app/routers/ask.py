import logging

import anthropic
from fastapi import APIRouter, HTTPException, Path

from app.config import ConfigError
from app.models.api import AskRequest, AskResponse
from app.services import answers, llm

router = APIRouter(tags=["ask"])
log = logging.getLogger("ask")


@router.post("/collections/{collection_id}/ask", response_model=AskResponse)
def ask(body: AskRequest, collection_id: str = Path(pattern=r"^[a-z0-9-]+$")):
    try:
        result = answers.ask(collection_id, body.question, [t.model_dump() for t in body.history],
                             body.filters.model_dump(mode="json"))
    except FileNotFoundError:
        raise HTTPException(404, f"Collection '{collection_id}' not found")
    except ConfigError as e:
        raise HTTPException(422, str(e))
    except llm.ModelUnavailable as e:
        raise HTTPException(502, str(e))
    except anthropic.APIStatusError as e:  # e.g. no credits, invalid key: show Claude's own reason
        log.warning("Claude API error %s: %s", e.status_code, e.message)
        raise HTTPException(502, llm.api_error_message(e))
    except (anthropic.APIError, llm.ModelRefusal):
        log.exception("answer generation failed")
        raise HTTPException(502, "Answer generation failed, please retry")
    answers.save(collection_id, result)
    return result
