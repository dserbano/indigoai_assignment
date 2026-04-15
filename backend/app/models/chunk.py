from sqlalchemy import Column, ForeignKey, Integer, String, Text
from pgvector.sqlalchemy import Vector

from app.core.db import Base

EMBEDDING_DIM = 1536

class Chunk(Base):
    __tablename__ = "chunks"

    id = Column(String, primary_key=True, index=True)
    document_id = Column(String, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)
    page_number = Column(Integer, nullable=True)
    embedding = Column(Vector(EMBEDDING_DIM), nullable=False)