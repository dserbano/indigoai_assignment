from __future__ import annotations

from typing import Iterable

from openai import OpenAI

from app.core.config import get_settings

settings = get_settings()


def _client() -> OpenAI:
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is not configured.")
    return OpenAI(api_key=settings.openai_api_key)


def embed_text(text: str) -> list[float]:
    clean = (text or "").strip()
    if not clean:
        return []
    response = _client().embeddings.create(
        model=settings.embedding_model,
        input=clean,
    )
    return list(response.data[0].embedding)


def embed_texts(texts: Iterable[str]) -> list[list[float]]:
    clean_texts = [t.strip() for t in texts if (t or "").strip()]
    if not clean_texts:
        return []

    response = _client().embeddings.create(
        model=settings.embedding_model,
        input=clean_texts,
    )
    return [list(item.embedding) for item in response.data]