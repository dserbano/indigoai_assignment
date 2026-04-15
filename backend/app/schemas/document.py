from datetime import datetime
from typing import List

from pydantic import BaseModel


class DocumentResponse(BaseModel):
    id: str
    filename: str
    tags: List[str]
    upload_date: datetime
    chunk_count: int
    file_type: str | None = None
    size_bytes: int | None = None


class UploadResponse(BaseModel):
    id: str
    filename: str
    message: str
    chunk_count: int
    tags: List[str]