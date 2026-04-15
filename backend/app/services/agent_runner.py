import asyncio
import json
from typing import Any

from langchain.agents import create_agent
from langchain.tools import tool
from langchain_openai import ChatOpenAI
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from app.core.config import get_settings

settings = get_settings()


def _result_to_text(result: Any) -> str:
    if hasattr(result, "content"):
        parts = []
        for item in result.content:
            text = getattr(item, "text", None)
            if text:
                parts.append(text)
            else:
                parts.append(str(item))
        if parts:
            return "\n".join(parts)
    return str(result)


async def _call_mcp_tool(tool_name: str, arguments: dict[str, Any]) -> str:
    headers: dict[str, str] = {}
    if settings.mcp_bearer_token:
        headers["Authorization"] = f"Bearer {settings.mcp_bearer_token}"

    async with streamablehttp_client(
        settings.mcp_url,
        headers=headers,
    ) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
            return _result_to_text(result)


def call_mcp_tool(tool_name: str, arguments: dict[str, Any]) -> str:
    return asyncio.run(_call_mcp_tool(tool_name, arguments))


@tool
def kb_list_documents(limit: int = 100, offset: int = 0, tag_filter: list[str] | None = None) -> str:
    """List documents in the knowledge base with metadata. Use when you need filenames, IDs, tags, or document metadata."""
    return call_mcp_tool(
        "list_documents",
        {"limit": limit, "offset": offset, "tag_filter": tag_filter},
    )


@tool
def kb_list_tags() -> str:
    """List all tags currently used in the knowledge base. Use when valid tag values are unknown."""
    return call_mcp_tool("list_tags", {})


@tool
def kb_search(query: str, top_k: int = 5) -> str:
    """Search the whole knowledge base semantically. Use for general questions with no tag or document restriction."""
    return call_mcp_tool("search", {"query": query, "top_k": top_k})


@tool
def kb_search_by_tag(query: str, tags: list[str], top_k: int = 5) -> str:
    """Search semantically, restricted to one or more tags. Use when the user explicitly wants a tag-limited search."""
    return call_mcp_tool(
        "search_by_tag",
        {"query": query, "tags": tags, "top_k": top_k},
    )


@tool
def kb_search_by_document(
    query: str,
    document_ids: list[str] | None = None,
    document_names: list[str] | None = None,
    top_k: int = 5,
) -> str:
    """Search semantically, restricted to one or more documents by ID or exact filename."""
    return call_mcp_tool(
        "search_by_document",
        {
            "query": query,
            "document_ids": document_ids,
            "document_names": document_names,
            "top_k": top_k,
        },
    )


agent = create_agent(
    model=ChatOpenAI(model=settings.openai_chat_model or "gpt-4o", temperature=0),
    tools=[
        kb_list_documents,
        kb_list_tags,
        kb_search,
        kb_search_by_tag,
        kb_search_by_document,
    ],
    system_prompt=(
        "You are a knowledge-base assistant.\n"
        "Use tools instead of guessing.\n"
        "Choose tools as follows:\n"
        "- kb_list_documents: when you need filenames, IDs, tags, or metadata.\n"
        "- kb_list_tags: when the user refers to categories or tags but the exact valid values are unclear.\n"
        "- kb_search: for general knowledge-base questions.\n"
        "- kb_search_by_tag: when the user explicitly wants tag-limited search.\n"
        "- kb_search_by_document: when the user names a specific document.\n"
        "Always mention source filenames in the final answer.\n"
        "If no relevant results are found, say so clearly."
    ),
    name="kb_agent",
)


def ask_agent(question: str) -> dict[str, Any]:
    result = agent.invoke(
        {"messages": [{"role": "user", "content": question}]}
    )

    messages = result.get("messages", [])
    if messages:
        last = messages[-1]
        answer = getattr(last, "content", None) or str(last)
    else:
        answer = str(result)

    sources: list[str] = []
    blob = json.dumps(result, default=str)

    marker = '"filename": "'
    start = 0
    while True:
        idx = blob.find(marker, start)
        if idx == -1:
            break
        idx += len(marker)
        end = blob.find('"', idx)
        if end == -1:
            break
        filename = blob[idx:end]
        if filename and filename not in sources:
            sources.append(filename)
        start = end + 1

    return {
        "answer": answer,
        "sources": sources,
    }