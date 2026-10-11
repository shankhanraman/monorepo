"""Local embeddings (fastembed, BAAI/bge-small-en-v1.5, 384-d). The model is baked into the image."""
import os
import threading

_model = None
_lock = threading.Lock()


def _get():
    global _model
    with _lock:
        if _model is None:
            from fastembed import TextEmbedding
            _model = TextEmbedding(os.environ.get("EMBED_MODEL", "BAAI/bge-small-en-v1.5"),
                                   cache_dir=os.environ.get("FASTEMBED_CACHE_PATH"))
    return _model


def passages(texts: list[str]) -> list:
    return list(_get().passage_embed(texts, batch_size=32))


def query(text: str):
    return next(iter(_get().query_embed([text])))
