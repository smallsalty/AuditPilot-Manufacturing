from pydantic import BaseModel


class ChatRequest(BaseModel):
    question: str


class ChatCitation(BaseModel):
    title: str
    content: str
    source_type: str


class ChatAnswerPayload(BaseModel):
    answer: str
    basis_level: str
    citations: list[ChatCitation]
    suggested_actions: list[str]
