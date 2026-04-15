from pydantic import BaseModel, Field


class AgentAskRequest(BaseModel):
    question: str = Field(min_length=1)


class AgentAskResponse(BaseModel):
    answer: str
    sources: list[str] = []