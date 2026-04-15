from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes_agent import router as agent_router
from app.api.routes_documents import router as documents_router
from app.api.routes_search import router as search_router
from app.api.routes_tags import router as tags_router
from app.core.config import get_settings, logger
from app.core.db import init_db
from app.mcp_server import mcp  # adjust if filename differs

settings = get_settings()
mcp_app = mcp.streamable_http_app()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Document Intelligence API...")
    init_db()

    # Start MCP session manager inside the mounted Starlette app
    async with mcp_app.router.lifespan_context(mcp_app):
        yield

    logger.info("Shutting down Document Intelligence API...")


app = FastAPI(
    title="Document Intelligence API",
    version="1.0.0",
    description="Backend for document ingestion, semantic retrieval, and MCP integration.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.backend_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition", "ETag"],
)

app.include_router(documents_router, prefix="/api", tags=["documents"])
app.include_router(tags_router, prefix="/api", tags=["tags"])
app.include_router(search_router, prefix="/api", tags=["search"])
app.include_router(agent_router, prefix="/api", tags=["agent"])

app.mount("/mcp", mcp_app)


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)