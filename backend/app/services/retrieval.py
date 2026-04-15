import json
import math
import re
from collections.abc import Iterable

from rank_bm25 import BM25Okapi
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.chunk import Chunk
from app.models.document import Document
from app.schemas.search import SearchResultItem
from app.services.embeddings import embed_text


TOKEN_PATTERN = re.compile(r"\b\w+\b", re.UNICODE)
RRF_K = 60  # Reciprocal Rank Fusion constant


def _tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_PATTERN.findall(text or "")]


def _safe_vector(values: Iterable[float] | None) -> list[float]:
    if values is None:
        return []
    return [float(v) for v in values]


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0

    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))

    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0

    return dot / (norm_a * norm_b)


def _fetch_eligible_rows(
    db: Session,
    tags: list[str] | None = None,
    document_ids: list[str] | None = None,
) -> list[tuple[Chunk, Document]]:
    stmt = (
        select(Chunk, Document)
        .join(Document, Chunk.document_id == Document.id)
    )

    if document_ids:
        stmt = stmt.where(Document.id.in_(document_ids))

    rows = db.execute(stmt).all()

    normalized_tags = {t.strip().lower() for t in (tags or []) if t.strip()}
    if not normalized_tags:
        return rows

    filtered: list[tuple[Chunk, Document]] = []
    for chunk, doc in rows:
        doc_tags = json.loads(doc.tags_json)
        doc_tag_set = {t.lower() for t in doc_tags}
        if normalized_tags.intersection(doc_tag_set):
            filtered.append((chunk, doc))

    return filtered


def _vector_rank(
    query: str,
    rows: list[tuple[Chunk, Document]],
) -> tuple[dict[str, int], dict[str, float]]:
    query_vector = embed_text(query)
    if not query_vector:
        return {}, {}

    scored: list[tuple[str, float]] = []

    for chunk, _doc in rows:
        chunk_vector = _safe_vector(chunk.embedding)
        similarity = _cosine_similarity(query_vector, chunk_vector)
        scored.append((chunk.id, similarity))

    scored.sort(key=lambda item: item[1], reverse=True)

    rank_map: dict[str, int] = {}
    score_map: dict[str, float] = {}

    for rank, (chunk_id, score) in enumerate(scored, start=1):
        rank_map[chunk_id] = rank
        score_map[chunk_id] = score

    return rank_map, score_map


def _bm25_rank(
    query: str,
    rows: list[tuple[Chunk, Document]],
) -> tuple[dict[str, int], dict[str, float]]:
    tokenized_query = _tokenize(query)
    if not tokenized_query:
        return {}, {}

    corpus = [_tokenize(chunk.text) for chunk, _doc in rows]
    if not corpus:
        return {}, {}

    bm25 = BM25Okapi(corpus)
    scores = bm25.get_scores(tokenized_query)

    scored: list[tuple[str, float]] = []
    for idx, (chunk, _doc) in enumerate(rows):
        scored.append((chunk.id, float(scores[idx])))

    scored.sort(key=lambda item: item[1], reverse=True)

    rank_map: dict[str, int] = {}
    score_map: dict[str, float] = {}

    for rank, (chunk_id, score) in enumerate(scored, start=1):
        rank_map[chunk_id] = rank
        score_map[chunk_id] = score

    return rank_map, score_map


def _rrf_score(rank: int | None) -> float:
    if rank is None:
        return 0.0
    return 1.0 / (RRF_K + rank)


def search_chunks(
    db: Session,
    query: str,
    top_k: int,
    tags: list[str] | None = None,
    document_ids: list[str] | None = None,
    retrieval_mode: str = "hybrid",
) -> list[SearchResultItem]:
    clean_query = (query or "").strip()
    if not clean_query:
        return []

    rows = _fetch_eligible_rows(
        db=db,
        tags=tags,
        document_ids=document_ids,
    )
    if not rows:
        return []

    chunk_lookup: dict[str, tuple[Chunk, Document]] = {
        chunk.id: (chunk, doc) for chunk, doc in rows
    }

    vector_ranks: dict[str, int] = {}
    vector_scores: dict[str, float] = {}
    bm25_ranks: dict[str, int] = {}
    bm25_scores: dict[str, float] = {}

    if retrieval_mode in {"vector", "hybrid"}:
        vector_ranks, vector_scores = _vector_rank(clean_query, rows)

    if retrieval_mode in {"bm25", "hybrid"}:
        bm25_ranks, bm25_scores = _bm25_rank(clean_query, rows)

    if retrieval_mode == "vector":
        ordered_ids = sorted(
            vector_scores.keys(),
            key=lambda chunk_id: vector_scores[chunk_id],
            reverse=True,
        )
        final_scores = {chunk_id: vector_scores[chunk_id] for chunk_id in ordered_ids}

    elif retrieval_mode == "bm25":
        ordered_ids = sorted(
            bm25_scores.keys(),
            key=lambda chunk_id: bm25_scores[chunk_id],
            reverse=True,
        )
        final_scores = {chunk_id: bm25_scores[chunk_id] for chunk_id in ordered_ids}

    else:
        all_chunk_ids = set(chunk_lookup.keys())
        final_scores = {
            chunk_id: _rrf_score(vector_ranks.get(chunk_id)) + _rrf_score(bm25_ranks.get(chunk_id))
            for chunk_id in all_chunk_ids
        }
        ordered_ids = sorted(
            final_scores.keys(),
            key=lambda chunk_id: final_scores[chunk_id],
            reverse=True,
        )

    results: list[SearchResultItem] = []
    for chunk_id in ordered_ids[:top_k]:
        chunk, doc = chunk_lookup[chunk_id]
        doc_tags = json.loads(doc.tags_json)

        results.append(
            SearchResultItem(
                chunk_id=chunk.id,
                text=chunk.text,
                score=float(final_scores[chunk_id]),
                document_id=doc.id,
                filename=doc.filename,
                tags=doc_tags,
                page_number=chunk.page_number,
            )
        )

    return results