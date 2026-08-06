"""Vector Channels dashboard plugin — backend API routes.

Mounted at /api/plugins/vector-channels/ by the dashboard plugin system.
This is a thin proxy that delegates to the VectorService so the desktop
plugin can use ctx.rest (which namespaces under /api/plugins/<id>).

All handlers call the same VectorService that /api/vector/* uses — the
single source of truth for agent registry, channel store, and dispatcher.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

log = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Import the vector service layer
# The vector package lives alongside the installed hermes-agent:
#   C:\Users\...\AppData\Local\hermes\hermes-agent\vector\src
# We try several candidate paths to find it.
# ---------------------------------------------------------------------------

_candidates = [
    # HERMES_HOME is C:\Users\...\AppData\Local\hermes
    # hermes-agent is a subdir of HERMES_HOME
    Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))) / "hermes-agent" / "vector" / "src",
    # Dev repo: Desktop\Hermes2\hermes-agent\vector\src
    Path.home() / "Desktop" / "Hermes2" / "hermes-agent" / "vector" / "src",
    # web_server.py relative path (parent.parent / vector / src)
    Path(__file__).resolve().parent.parent.parent.parent.parent / "hermes-agent" / "vector" / "src",
    Path(__file__).resolve().parent.parent.parent.parent.parent / "vector" / "src",
]
for _candidate in _candidates:
    if _candidate.is_dir() and str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

try:
    from vector.service import VectorService
    from vector.runtime import AgentRuntime
except ImportError as e:
    log.warning("vector-channels plugin: could not import vector module: %s", e)
    VectorService = None  # type: ignore[assignment]
    AgentRuntime = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Service init (lazy) — same pattern as web_server.py
# ---------------------------------------------------------------------------

_service_instance = None


def _get_service():
    global _service_instance
    if _service_instance is not None:
        return _service_instance
    if VectorService is None:
        return None
    _home = os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))
    _vec_dir = Path(_home) / "vector"
    _vec_dir.mkdir(parents=True, exist_ok=True)
    _service_instance = VectorService(
        db_path=str(_vec_dir / "vector.db"),
        agents_yaml=str(_vec_dir / "agents.yaml"),
        runtime=AgentRuntime(),
    )
    return _service_instance


def _err(code: str, message: str, status: int = 500) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "retryable": False}},
    )


def _agent_to_dict(profile) -> dict:
    return {
        "handle": profile.handle,
        "description": getattr(profile, "description", None),
        "model": profile.model,
        "provider": profile.provider,
        "tools": profile.tools or [],
    }


def _channel_to_dict(ch) -> dict:
    return {"id": ch.id, "name": ch.name, "member_count": getattr(ch, "member_count", None)}


def _message_to_dict(msg) -> dict:
    import time
    from datetime import datetime, timezone
    return {
        "id": msg.id,
        "channel_id": msg.channel_id,
        "author_handle": msg.author_handle,
        "body": msg.body,
        "mentions": getattr(msg, "mentions", []),
        "created_at": datetime.fromtimestamp(
            getattr(msg, "created_at", 0) or 0, tz=timezone.utc
        ).isoformat(),
    }


# ---------------------------------------------------------------------------
# Endpoints — mirror /api/vector/* but under /api/plugins/vector-channels/
# ---------------------------------------------------------------------------

@router.get("/health")
async def health() -> JSONResponse:
    svc = _get_service()
    if svc is None:
        return _err("VECTOR_NOT_INITIALIZED", "Vector module not loaded", 503)
    return JSONResponse({"status": "ok", "version": "0.1.0", "storage": svc.health_storage()})


@router.get("/agents")
async def list_agents() -> JSONResponse:
    svc = _get_service()
    if svc is None:
        return _err("VECTOR_NOT_INITIALIZED", "Vector module not loaded", 503)
    agents = svc.list_agents()
    return JSONResponse({"agents": [_agent_to_dict(a) for a in agents]})


@router.post("/agents")
async def create_agent(request: Request) -> JSONResponse:
    svc = _get_service()
    if svc is None:
        return _err("VECTOR_NOT_INITIALIZED", "Vector module not loaded", 503)
    try:
        body = await request.json()
        profile = svc.create_agent(
            handle=body.get("handle"),
            system_prompt=body.get("system_prompt"),
            description=body.get("description"),
            model=body.get("model"),
            provider=body.get("provider"),
            tools=body.get("tools"),
            fallback_models=body.get("fallback_models"),
        )
        return JSONResponse(_agent_to_dict(profile), status_code=201)
    except Exception as e:
        return _err("VECTOR_BAD_REQUEST", str(e), 400)


@router.get("/channels")
async def list_channels() -> JSONResponse:
    svc = _get_service()
    if svc is None:
        return _err("VECTOR_NOT_INITIALIZED", "Vector module not loaded", 503)
    channels = svc.list_channels()
    return JSONResponse({"channels": [_channel_to_dict(ch) for ch in channels]})


@router.post("/channels")
async def create_channel(request: Request) -> JSONResponse:
    svc = _get_service()
    if svc is None:
        return _err("VECTOR_NOT_INITIALIZED", "Vector module not loaded", 503)
    try:
        body = await request.json()
        members = body.get("members", [])
        # Always include 'human' as a member so they can post messages.
        if "human" not in members:
            members = ["human", *members]
        ch = svc.create_channel(body["name"], members)
        return JSONResponse(_channel_to_dict(ch), status_code=201)
    except Exception as e:
        return _err("VECTOR_BAD_REQUEST", str(e), 400)


@router.get("/channels/{channel_id}/members")
async def get_members(channel_id: str) -> JSONResponse:
    svc = _get_service()
    if svc is None:
        return _err("VECTOR_NOT_INITIALIZED", "Vector module not loaded", 503)
    try:
        members = svc.list_members(channel_id)
        return JSONResponse({"members": members})
    except Exception as e:
        return _err("VECTOR_CHANNEL_NOT_FOUND", str(e), 404)


@router.get("/channels/{channel_id}/messages")
async def get_history(channel_id: str) -> JSONResponse:
    svc = _get_service()
    if svc is None:
        return _err("VECTOR_NOT_INITIALIZED", "Vector module not loaded", 503)
    try:
        limit = 50
        messages = svc.history(channel_id, limit=limit)
        return JSONResponse({"messages": [_message_to_dict(m) for m in messages]})
    except Exception as e:
        return _err("VECTOR_CHANNEL_NOT_FOUND", str(e), 404)


@router.post("/channels/{channel_id}/messages")
async def post_message(channel_id: str, request: Request) -> JSONResponse:
    svc = _get_service()
    if svc is None:
        return _err("VECTOR_NOT_INITIALIZED", "Vector module not loaded", 503)
    try:
        body = await request.json()
        result = svc.post_and_dispatch(
            channel_id,
            body.get("author_handle", "human"),
            body.get("body", ""),
            dispatch=body.get("dispatch", True),
        )
        return JSONResponse({
            "message": _message_to_dict(result.message),
            "dispatch": result.dispatch.model_dump() if result.dispatch and hasattr(result.dispatch, "model_dump") else None,
            "messages": [_message_to_dict(m) for m in result.messages],
        })
    except Exception as e:
        return _err("VECTOR_BAD_REQUEST", str(e), 400)
