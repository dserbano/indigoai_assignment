from typing import Literal

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)
    mode: Literal["all", "tag", "document"] = "all"
    tags: list[str] | None = None
    document_ids: list[str] | None = None
    retrieval_mode: Literal["vector", "bm25", "hybrid"] = "hybrid"


class SearchResultItem(BaseModel):
    chunk_id: str
    text: str
    score: float
    document_id: str
    filename: str
    tags: list[str]
    page_number: int | None = None


class SearchResponse(BaseModel):
    query: str
    top_k: int
    retrieval_mode: Literal["vector", "bm25", "hybrid"]
    results: list[SearchResultItem]