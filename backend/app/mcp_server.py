from __future__ import annotations

import json
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP
from sqlalchemy.orm import Session

from app.core.config import get_settings, logger
from app.core.db import SessionLocal, init_db
from app.models.document import Document
from app.services.retrieval import search_chunks

settings = get_settings()

mcp = FastMCP(
    name="Knowledge Base MCP Server",
    instructions=(
        "This server exposes a document knowledge base as tools. "
        "Use list_documents to discover available documents and their metadata. "
        "Use list_tags to discover available tags. "
        "Use search for general knowledge-base search when no filters are needed. "
        "Use search_by_tag when the user wants search limited to one or more tags. "
        "Use search_by_document when the user mentions a specific document name or document ID. "
        "The default retrieval mode is hybrid, which combines semantic vector search with lexical BM25 search."
    ),
    json_response=True,
)


def get_db_session() -> Session:
    return SessionLocal()


def document_to_dict(doc: Document) -> dict[str, Any]:
    return {
        "id": doc.id,
        "name": doc.filename,
        "tags": json.loads(doc.tags_json),
        "upload_date": doc.upload_date.isoformat(),
        "chunk_count": doc.chunk_count,
        "file_type": doc.file_type,
        "size_bytes": doc.size_bytes,
    }


@mcp.tool(
    name="list_documents",
    description=(
        "Return documents currently in the knowledge base, including metadata. "
        "Use this before search_by_document when you need document names, IDs, tags, "
        "file types, or upload dates."
    ),
)
def list_documents(
    limit: int = 100,
    offset: int = 0,
    tag_filter: list[str] | None = None,
) -> dict[str, Any]:
    if limit < 1 or limit > 500:
        raise ValueError("limit must be between 1 and 500")
    if offset < 0:
        raise ValueError("offset must be >= 0")

    db = get_db_session()
    try:
        docs = db.query(Document).order_by(Document.upload_date.desc()).all()
        normalized_tags = {t.strip().lower() for t in (tag_filter or []) if t.strip()}

        items: list[dict[str, Any]] = []
        for doc in docs:
            tags = json.loads(doc.tags_json)
            tag_set = {t.lower() for t in tags}
            if normalized_tags and not normalized_tags.intersection(tag_set):
                continue
            items.append(document_to_dict(doc))

        sliced = items[offset : offset + limit]
        return {
            "documents": sliced,
            "offset": offset,
            "limit": limit,
            "returned": len(sliced),
            "total_matching": len(items),
        }
    finally:
        db.close()


@mcp.tool(
    name="list_tags",
    description=(
        "Return all unique tags that are assigned to at least one document. "
        "Use this before search_by_tag when the exact tag values are unknown."
    ),
)
def list_tags() -> dict[str, Any]:
    db = get_db_session()
    try:
        docs = db.query(Document).all()
        all_tags: set[str] = set()

        for doc in docs:
            for tag in json.loads(doc.tags_json):
                all_tags.add(tag)

        return {"tags": sorted(all_tags), "count": len(all_tags)}
    finally:
        db.close()


@mcp.tool(
    name="search",
    description=(
        "Search across the entire knowledge base. "
        "Default retrieval_mode is 'hybrid', which combines vector semantic search with BM25 lexical matching. "
        "Use 'vector' for semantic-only search, 'bm25' for keyword-heavy search, and 'hybrid' for the best general default. "
        "Returns the top-k most relevant chunks with source document metadata."
    ),
)
def search(
    query: str,
    top_k: int = 5,
    retrieval_mode: Literal["vector", "bm25", "hybrid"] = "hybrid",
) -> dict[str, Any]:
    if not query.strip():
        raise ValueError("query must not be empty")
    if top_k < 1 or top_k > settings.max_top_k:
        raise ValueError(f"top_k must be between 1 and {settings.max_top_k}")

    db = get_db_session()
    try:
        results = search_chunks(
            db=db,
            query=query,
            top_k=top_k,
            tags=None,
            document_ids=None,
            retrieval_mode=retrieval_mode,
        )
        return {
            "query": query,
            "top_k": top_k,
            "retrieval_mode": retrieval_mode,
            "results": [r.model_dump() for r in results],
        }
    finally:
        db.close()


@mcp.tool(
    name="search_by_tag",
    description=(
        "Search restricted to documents matching one or more specified tags. "
        "Default retrieval_mode is 'hybrid', which combines vector semantic search with BM25 lexical matching. "
        "Use this when the user explicitly asks for information from a category such as compliance, hr, onboarding, or product."
    ),
)
def search_by_tag(
    query: str,
    tags: list[str],
    top_k: int = 5,
    retrieval_mode: Literal["vector", "bm25", "hybrid"] = "hybrid",
) -> dict[str, Any]:
    if not query.strip():
        raise ValueError("query must not be empty")
    if not tags:
        raise ValueError("tags must not be empty")
    if top_k < 1 or top_k > settings.max_top_k:
        raise ValueError(f"top_k must be between 1 and {settings.max_top_k}")

    normalized_tags = sorted({t.strip().lower() for t in tags if t.strip()})
    if not normalized_tags:
        raise ValueError("tags must contain at least one non-empty value")

    db = get_db_session()
    try:
        results = search_chunks(
            db=db,
            query=query,
            top_k=top_k,
            tags=normalized_tags,
            document_ids=None,
            retrieval_mode=retrieval_mode,
        )
        return {
            "query": query,
            "tags": normalized_tags,
            "top_k": top_k,
            "retrieval_mode": retrieval_mode,
            "results": [r.model_dump() for r in results],
        }
    finally:
        db.close()


@mcp.tool(
    name="search_by_document",
    description=(
        "Search restricted to one or more specific documents. "
        "Default retrieval_mode is 'hybrid', which combines vector semantic search with BM25 lexical matching. "
        "Use this when the user names a document or when document IDs are already known. "
        "You may pass document_ids, document_names, or both."
    ),
)
def search_by_document(
    query: str,
    document_ids: list[str] | None = None,
    document_names: list[str] | None = None,
    top_k: int = 5,
    retrieval_mode: Literal["vector", "bm25", "hybrid"] = "hybrid",
) -> dict[str, Any]:
    if not query.strip():
        raise ValueError("query must not be empty")
    if not document_ids and not document_names:
        raise ValueError("Provide at least one of document_ids or document_names")
    if top_k < 1 or top_k > settings.max_top_k:
        raise ValueError(f"top_k must be between 1 and {settings.max_top_k}")

    db = get_db_session()
    try:
        resolved_ids = set(document_ids or [])

        if document_names:
            wanted_names = {name.strip().lower() for name in document_names if name.strip()}
            if wanted_names:
                docs = db.query(Document).all()
                for doc in docs:
                    if doc.filename.strip().lower() in wanted_names:
                        resolved_ids.add(doc.id)

        if not resolved_ids:
            return {
                "query": query,
                "document_ids": [],
                "top_k": top_k,
                "retrieval_mode": retrieval_mode,
                "results": [],
                "warning": "No matching document_ids could be resolved from the provided names/IDs.",
            }

        results = search_chunks(
            db=db,
            query=query,
            top_k=top_k,
            tags=None,
            document_ids=sorted(resolved_ids),
            retrieval_mode=retrieval_mode,
        )
        return {
            "query": query,
            "document_ids": sorted(resolved_ids),
            "top_k": top_k,
            "retrieval_mode": retrieval_mode,
            "results": [r.model_dump() for r in results],
        }
    finally:
        db.close()


def main() -> None:
    logger.info("Starting standalone MCP server...")
    init_db()
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()