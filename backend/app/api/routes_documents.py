import json
import os

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.models.chunk import Chunk
from app.models.document import Document
from app.schemas.document import DocumentResponse, UploadResponse
from app.services.ingestion import ingest_document

router = APIRouter()


@router.get("/documents", response_model=list[DocumentResponse])
def list_documents(db: Session = Depends(get_db)):
    docs = db.query(Document).order_by(Document.upload_date.desc()).all()
    return [
        DocumentResponse(
            id=doc.id,
            filename=doc.filename,
            tags=json.loads(doc.tags_json),
            upload_date=doc.upload_date,
            chunk_count=doc.chunk_count,
            file_type=doc.file_type,
            size_bytes=doc.size_bytes,
        )
        for doc in docs
    ]


@router.post("/documents", response_model=UploadResponse)
def upload_document(
    file: UploadFile = File(...),
    tags: str = Form(default="[]"),
    db: Session = Depends(get_db),
):
    settings = get_settings()

    try:
        parsed_tags = json.loads(tags)
        if not isinstance(parsed_tags, list):
            raise ValueError("tags must be a JSON array")
        normalized_tags = sorted(
            {str(tag).strip().lower() for tag in parsed_tags if str(tag).strip()}
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid tags payload: {exc}") from exc

    allowed_suffixes = {".pdf", ".txt"}
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in allowed_suffixes:
        raise HTTPException(status_code=400, detail="Only PDF and TXT files are supported.")

    try:
        return ingest_document(
            db=db,
            file=file,
            tags=normalized_tags,
            upload_dir=settings.upload_dir,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Upload failed: {exc}") from exc


@router.delete("/documents/{document_id}")
def delete_document(document_id: str, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    db.query(Chunk).filter(Chunk.document_id == document_id).delete()

    try:
        if os.path.exists(doc.storage_path):
            os.remove(doc.storage_path)
    except OSError:
        pass

    db.delete(doc)
    db.commit()

    return {"message": "Document deleted."}


@router.get("/documents/{document_id}/download")
def download_document(document_id: str, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == document_id).first()

    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    if not os.path.exists(doc.storage_path):
        raise HTTPException(status_code=404, detail="File not found on disk.")

    return FileResponse(
        path=doc.storage_path,
        filename=doc.filename,
        media_type="application/octet-stream",
    )