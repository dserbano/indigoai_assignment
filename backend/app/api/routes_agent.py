from fastapi import APIRouter, HTTPException

from app.schemas.agent import AgentAskRequest, AgentAskResponse
from app.services.agent_runner import ask_agent

router = APIRouter()


@router.post("/agent/ask", response_model=AgentAskResponse)
def agent_ask(payload: AgentAskRequest):
    try:
        result = ask_agent(payload.question)
        return AgentAskResponse(
            answer=result.get("answer", ""),
            sources=result.get("sources", []),
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Agent failed: {exc}") from exc