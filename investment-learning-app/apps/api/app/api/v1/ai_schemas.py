from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class ConversationCreateRequest(BaseModel):
    journal_id: UUID | None = None


class ConversationResponse(BaseModel):
    id: UUID
    journal_id: UUID | None


class MessageCreateRequest(BaseModel):
    content: str


class SourceResponse(BaseModel):
    type: str
    id: str | None
    title: str
    as_of: str | None
    source: str
    delay_seconds: int | None = None


class MessageResponse(BaseModel):
    id: UUID
    role: str
    content: str
    model: str | None
    prompt_version: str | None
    sources: list[SourceResponse]
    degraded: bool
    created_at: datetime


class MessageFeedbackRequest(BaseModel):
    feedback: Literal["HELPFUL", "NOT_HELPFUL", "REPORTED"]
    comment: str | None = None
