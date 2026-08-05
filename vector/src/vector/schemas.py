"""Pydantic request/response schemas for the Vector gateway API.

Defines the HTTP contract for /api/vector endpoints. All request and
response models live here so the router and service can import them
without circular dependencies.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Constraints
# ---------------------------------------------------------------------------

MAX_MESSAGE_LENGTH = 32_000
MAX_CHANNEL_NAME_LENGTH = 128
MAX_HISTORY_LIMIT = 200
MIN_HISTORY_LIMIT = 1


# ---------------------------------------------------------------------------
# Error envelope
# ---------------------------------------------------------------------------


class VectorError(BaseModel):
    """Single error detail inside the envelope."""

    code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable message")
    retryable: bool = False


class VectorErrorEnvelope(BaseModel):
    """Stable error response wrapper."""

    error: VectorError


# ---------------------------------------------------------------------------
# Agent schemas
# ---------------------------------------------------------------------------


class AgentOut(BaseModel):
    """Agent profile as returned by the API."""

    handle: str
    description: Optional[str] = None
    model: Optional[str] = None
    provider: Optional[str] = None
    tools: list[str] = Field(default_factory=list)


class AgentListResponse(BaseModel):
    agents: list[AgentOut] = Field(default_factory=list)


class CreateAgentRequest(BaseModel):
    handle: str = Field(..., min_length=1, max_length=64)
    system_prompt: str = Field(..., min_length=1)
    description: Optional[str] = None
    model: Optional[str] = None
    provider: Optional[str] = None
    tools: list[str] = Field(default_factory=list)
    fallback_models: list[str] = Field(default_factory=list)

    @field_validator("handle")
    @classmethod
    def normalize_handle(cls, v: str) -> str:
        v = v.strip().lower()
        if not v:
            raise ValueError("handle must not be empty")
        return v


# ---------------------------------------------------------------------------
# Channel schemas
# ---------------------------------------------------------------------------


class ChannelOut(BaseModel):
    id: str
    name: str
    member_count: int = 0


class ChannelListResponse(BaseModel):
    channels: list[ChannelOut] = Field(default_factory=list)


class CreateChannelRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=MAX_CHANNEL_NAME_LENGTH)
    members: list[str] = Field(default_factory=list)


class MemberListResponse(BaseModel):
    members: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Message schemas
# ---------------------------------------------------------------------------


class MessageOut(BaseModel):
    id: str
    channel_id: str
    author_handle: str
    body: str
    mentions: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class HistoryResponse(BaseModel):
    messages: list[MessageOut] = Field(default_factory=list)


class PostMessageRequest(BaseModel):
    author_handle: str = Field(..., min_length=1)
    body: str = Field(..., min_length=1, max_length=MAX_MESSAGE_LENGTH)
    dispatch: bool = True

    @field_validator("author_handle")
    @classmethod
    def normalize_author(cls, v: str) -> str:
        v = v.strip().lower()
        if not v:
            raise ValueError("author_handle must not be empty")
        return v


# ---------------------------------------------------------------------------
# Dispatch result schemas
# ---------------------------------------------------------------------------


class DispatchEntryOut(BaseModel):
    handle: str
    depth: int = 0
    status: str = "ok"
    response: str = ""


class DispatchResultOut(BaseModel):
    entries: list[DispatchEntryOut] = Field(default_factory=list)
    recursion_exceeded: bool = False
    error: Optional[str] = None


class PostMessageResponse(BaseModel):
    message: MessageOut
    dispatch: Optional[DispatchResultOut] = None
    messages: list[MessageOut] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.1.0"
    storage: str = "sqlite"
