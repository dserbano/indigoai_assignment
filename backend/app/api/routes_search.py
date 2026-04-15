from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.schemas.search import SearchRequest, SearchResponse
from app.services.retrieval import search_chunks

router = APIRouter()


@router.post("/search", response_model=SearchResponse)
def search_documents(payload: SearchRequest, db: Session = Depends(get_db)):
    settings = get_settings()

    if payload.mode == "tag" and not payload.tags:
        raise HTTPException(status_code=400, detail="tags are required when mode='tag'")

    if payload.mode == "document" and not payload.document_ids:
        raise HTTPException(status_code=400, detail="document_ids are required when mode='document'")

    top_k = min(payload.top_k, settings.max_top_k)

    results = search_chunks(
        db=db,
        query=payload.query,
        top_k=top_k,
        tags=payload.tags if payload.mode == "tag" else None,
        document_ids=payload.document_ids if payload.mode == "document" else None,
        retrieval_mode=payload.retrieval_mode,
    )

    return SearchResponse(
        query=payload.query,
        top_k=top_k,
        retrieval_mode=payload.retrieval_mode,
        results=results,
    )