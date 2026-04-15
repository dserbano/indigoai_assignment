import json

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.document import Document

router = APIRouter()


@router.get("/tags")
def list_tags(db: Session = Depends(get_db)):
    docs = db.query(Document).all()
    all_tags: set[str] = set()

    for doc in docs:
        for tag in json.loads(doc.tags_json):
            all_tags.add(tag)

    return {"tags": sorted(all_tags)}