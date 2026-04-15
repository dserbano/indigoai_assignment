import json
import os
import uuid
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.models.chunk import Chunk
from app.models.document import Document
from app.schemas.document import UploadResponse
from app.services.embeddings import embed_texts
from app.services.parser import parse_document
from app.utils.hashing import sha256_bytes


def chunk_text(
    pages: list[dict],
    chunk_size: int = 800,
    chunk_overlap: int = 120,
) -> list[dict]:
    chunks: list[dict] = []

    for page in pages:
        text = (page.get("text") or "").strip()
        if not text:
            continue

        start = 0
        chunk_index = 0

        while start < len(text):
            end = start + chunk_size
            chunk_text_value = text[start:end].strip()

            if chunk_text_value:
                chunks.append(
                    {
                        "chunk_index": chunk_index,
                        "text": chunk_text_value,
                        "page_number": page.get("page_number"),
                    }
                )
                chunk_index += 1

            start += max(1, chunk_size - chunk_overlap)

    return chunks


def ingest_document(
    db: Session,
    file: UploadFile,
    tags: list[str],
    upload_dir: str,
) -> UploadResponse:
    file_bytes = file.file.read()
    file_hash = sha256_bytes(file_bytes)

    existing = db.query(Document).filter(Document.file_hash == file_hash).first()
    if existing:
        return UploadResponse(
            id=existing.id,
            filename=existing.filename,
            message="Duplicate file detected. Existing document returned.",
            chunk_count=existing.chunk_count,
            tags=json.loads(existing.tags_json),
        )

    document_id = str(uuid.uuid4())
    safe_name = f"{document_id}_{Path(file.filename).name}"
    storage_path = os.path.join(upload_dir, safe_name)

    with open(storage_path, "wb") as f:
        f.write(file_bytes)

    _, pages, file_type = parse_document(storage_path, file.filename, file_bytes)
    chunks = chunk_text(pages)

    doc = Document(
        id=document_id,
        filename=file.filename,
        file_hash=file_hash,
        file_type=file_type,
        size_bytes=len(file_bytes),
        tags_json=json.dumps(tags),
        chunk_count=len(chunks),
        storage_path=storage_path,
    )
    db.add(doc)
    db.flush()

    texts = [chunk["text"] for chunk in chunks]
    vectors = embed_texts(texts)

    if len(vectors) != len(chunks):
        raise ValueError(
            f"Embedding count mismatch: got {len(vectors)} vectors for {len(chunks)} chunks."
        )

    for idx, chunk in enumerate(chunks):
        db.add(
            Chunk(
                id=str(uuid.uuid4()),
                document_id=document_id,
                chunk_index=idx,
                text=chunk["text"],
                page_number=chunk.get("page_number"),
                embedding=vectors[idx],
            )
        )

    db.commit()

    return UploadResponse(
        id=document_id,
        filename=file.filename,
        message=f'Uploaded "{file.filename}" successfully.',
        chunk_count=len(chunks),
        tags=tags,
    )