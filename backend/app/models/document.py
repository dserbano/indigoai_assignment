from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from app.core.db import Base


class Document(Base):
    __tablename__ = "documents"

    id = Column(String, primary_key=True, index=True)
    filename = Column(String, nullable=False, unique=True, index=True)
    file_hash = Column(String, nullable=False, unique=True, index=True)
    file_type = Column(String, nullable=False)
    size_bytes = Column(Integer, nullable=False)
    tags_json = Column(Text, nullable=False, default="[]")
    upload_date = Column(DateTime, nullable=False, default=datetime.utcnow)
    chunk_count = Column(Integer, nullable=False, default=0)
    storage_path = Column(String, nullable=False)