"""FastAPI router for the Vector gateway API.

Exposes ``create_vector_router(get_service)`` which mounts all Vector
endpoints under a common prefix (typically ``/api/vector``).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from fastapi import APIRouter, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from vector.schemas import (
    AgentListResponse,
    AgentOut,
    ChannelListResponse,
    ChannelOut,
    CreateAgentRequest,
    CreateChannelRequest,
    DispatchEntryOut,
    DispatchResultOut,
    HealthResponse,
    HistoryResponse,
    MemberListResponse,
    MessageOut,
    PostMessageRequest,
    PostMessageResponse,
    VectorErrorEnvelope,
    VectorError as VectorErrorSchema,
)
from vector.service import (
    AgentAlreadyExistsError,
    AgentNotFoundError,
    ChannelNotFound,
    ChannelTooLargeError,
    MemberAlreadyExistsError,
    VectorError,
    VectorValidationError,
)


def _error_response(code: str, message: str, status: int, retryable: bool = False) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content=VectorErrorEnvelope(
            error=VectorErrorSchema(code=code, message=message, retryable=retryable)
        ).model_dump(),
    )


def _vector_error_handler(exc: VectorError) -> JSONResponse:
    return _error_response(exc.code, exc.message, exc.http_status, exc.retryable)


def create_vector_router(get_service: Callable) -> APIRouter:
    """Create the Vector API router.

    ``get_service`` is a callable that returns a ``VectorService``
    instance.  This indirection lets the gateway own lifecycle while
    the router stays stateless.
    """

    router = APIRouter()

    # Register exception handlers on the router's underlying APIRouter.
    # FastAPI will route these per-router when mounted via include_router.

    # -------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------

    def _agent_to_out(profile) -> AgentOut:
        return AgentOut(
            handle=profile.handle,
            description=getattr(profile, "description", None),
            model=profile.model,
            provider=profile.provider,
            tools=profile.tools or [],
        )

    def _channel_to_out(ch) -> ChannelOut:
        return ChannelOut(id=ch.id, name=ch.name)

    def _message_to_out(msg) -> MessageOut:
        return MessageOut(
            id=msg.id,
            channel_id=msg.channel_id,
            author_handle=msg.author_handle,
            body=msg.body,
            mentions=getattr(msg, "mentions", []),
            created_at=datetime.fromtimestamp(
                getattr(msg, "created_at", 0) or 0, tz=timezone.utc
            ),
        )

    # -------------------------------------------------------------------
    # Endpoints
    # -------------------------------------------------------------------

    @router.get("/health")
    def health():
        svc = get_service()
        return HealthResponse(status="ok", version="0.1.0", storage=svc.health_storage)

    @router.get("/agents")
    def list_agents():
        svc = get_service()
        agents = svc.list_agents()
        return AgentListResponse(agents=[_agent_to_out(a) for a in agents])

    @router.post("/agents", status_code=201)
    def create_agent(req: CreateAgentRequest):
        svc = get_service()
        try:
            profile = svc.create_agent(
                handle=req.handle,
                system_prompt=req.system_prompt,
                description=req.description,
                model=req.model,
                provider=req.provider,
                tools=req.tools,
                fallback_models=req.fallback_models,
            )
        except AgentAlreadyExistsError as e:
            return _vector_error_handler(e)
        except AgentNotFoundError as e:
            return _vector_error_handler(e)
        return _agent_to_out(profile)

    @router.get("/channels")
    def list_channels():
        svc = get_service()
        channels = svc.list_channels()
        return ChannelListResponse(channels=[_channel_to_out(ch) for ch in channels])

    @router.post("/channels", status_code=201)
    def create_channel(req: CreateChannelRequest):
        svc = get_service()
        try:
            ch = svc.create_channel(name=req.name, members=req.members)
        except AgentNotFoundError as e:
            return _vector_error_handler(e)
        except ChannelTooLargeError as e:
            return _vector_error_handler(e)
        return _channel_to_out(ch)

    @router.get("/channels/{channel_id}/members")
    def list_members(channel_id: str):
        svc = get_service()
        try:
            members = svc.list_members(channel_id)
        except ChannelNotFound as e:
            return _vector_error_handler(e)
        return MemberListResponse(members=members)

    @router.get("/channels/{channel_id}/messages")
    def get_history(channel_id: str, limit: int = 50):
        svc = get_service()
        try:
            messages = svc.history(channel_id, limit=limit)
        except ChannelNotFound as e:
            return _vector_error_handler(e)
        return HistoryResponse(messages=[_message_to_out(msg) for msg in messages])

    @router.post("/channels/{channel_id}/messages")
    def post_message(channel_id: str, req: PostMessageRequest):
        svc = get_service()
        try:
            result = svc.post_and_dispatch(
                channel_id=channel_id,
                author_handle=req.author_handle,
                body=req.body,
                dispatch=req.dispatch,
            )
        except ChannelNotFound as e:
            return _vector_error_handler(e)
        except VectorError as e:
            return _vector_error_handler(e)

        messages_out = [_message_to_out(msg) for msg in result.messages]

        dispatch_out = None
        if result.dispatch:
            dispatch_out = DispatchResultOut(
                entries=[
                    DispatchEntryOut(
                        handle=e.handle,
                        depth=e.depth,
                        status=e.status,
                        response=e.response,
                    )
                    for e in result.dispatch.entries
                ],
                recursion_exceeded=result.dispatch.recursion_exceeded,
                error=result.dispatch.error,
            )

        return PostMessageResponse(
            message=_message_to_out(result.message),
            dispatch=dispatch_out,
            messages=messages_out,
        )

    return router
