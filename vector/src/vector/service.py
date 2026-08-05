"""VectorService — composition boundary between FastAPI handlers and the domain.

Handlers never touch SQLite or YAML directly; they go through this service.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from vector.channel import (
    Channel,
    ChannelNotFoundError,
    ChannelStore,
)
from vector.dispatcher import Dispatcher, DispatchResult
from vector.mention import extract_mentions
from vector.profile import AgentProfile, AgentRegistry
from vector.runtime import AgentRuntime


# ---------------------------------------------------------------------------
# Input dataclass (HTTP-agnostic)
# ---------------------------------------------------------------------------


@dataclass
class CreateAgentInput:
    handle: str
    system_prompt: str
    description: Optional[str] = None
    model: Optional[str] = None
    provider: Optional[str] = None
    tools: list[str] = field(default_factory=list)
    fallback_models: list[str] = field(default_factory=list)


@dataclass
class PostMessageResult:
    """Result of post_and_dispatch — returned to the API layer."""

    message: object  # Message dataclass from channel.py
    dispatch: Optional[DispatchResult] = None
    messages: list[object] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Domain exceptions (mapped by API layer)
# ---------------------------------------------------------------------------


class VectorError(Exception):
    """Base domain error with a stable code."""

    code: str = "VECTOR_INTERNAL_ERROR"
    http_status: int = 500
    retryable: bool = False

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class AgentAlreadyExistsError(VectorError):
    code = "VECTOR_AGENT_EXISTS"
    http_status = 409


class AgentNotFoundError(VectorError):
    code = "VECTOR_AGENT_NOT_FOUND"
    http_status = 404


class ChannelNotFound(VectorError):
    code = "VECTOR_CHANNEL_NOT_FOUND"
    http_status = 404


class MemberAlreadyExistsError(VectorError):
    code = "VECTOR_MEMBER_EXISTS"
    http_status = 409


class ChannelTooLargeError(VectorError):
    code = "VECTOR_CHANNEL_TOO_LARGE"
    http_status = 409


class VectorValidationError(VectorError):
    code = "VECTOR_VALIDATION_ERROR"
    http_status = 422


# ---------------------------------------------------------------------------
# VectorService
# ---------------------------------------------------------------------------


class VectorService:
    """Service layer composing AgentRegistry, ChannelStore, and Dispatcher.

    Production composition reuses ``$HERMES_HOME/vector/agents.yaml`` and
    ``$HERMES_HOME/vector/vector.db`` to match the CLI.  Tests inject
    temporary paths and a fake delegate runtime.
    """

    def __init__(
        self,
        db_path: str,
        agents_yaml: str,
        runtime: AgentRuntime,
        *,
        max_dispatch_depth: int = 3,
    ) -> None:
        self._db_path = db_path
        self._agents_yaml = agents_yaml
        self._runtime = runtime

        # Load existing agents from YAML
        yaml_path = Path(agents_yaml)
        if yaml_path.exists():
            self._registry = AgentRegistry.load_from_yaml(str(yaml_path))
        else:
            self._registry = AgentRegistry()

        self._store = ChannelStore(db_path, registry=self._registry)
        self._dispatcher = Dispatcher(
            store=self._store,
            runtime=runtime,
            registry=self._registry,
            max_depth=max_dispatch_depth,
        )

    # -- agents -------------------------------------------------------------

    def list_agents(self) -> list[AgentProfile]:
        return self._registry.all()

    def create_agent(
        self,
        handle: str = None,
        system_prompt: str = None,
        *,
        request: CreateAgentInput | dict | None = None,
        description: str | None = None,
        model: str | None = None,
        provider: str | None = None,
        tools: list[str] | None = None,
        fallback_models: list[str] | None = None,
    ) -> AgentProfile:
        if request is not None:
            if isinstance(request, dict):
                request = CreateAgentInput(**request)
            handle = request.handle
            system_prompt = request.system_prompt
            description = request.description
            model = request.model
            provider = request.provider
            tools = request.tools
            fallback_models = request.fallback_models

        # Check for conflict
        try:
            self._registry.get(handle)
            raise AgentAlreadyExistsError(
                f"Agent '{handle}' already exists"
            )
        except KeyError:
            pass  # Not found — OK to create

        profile = AgentProfile(
            handle=handle,
            system_prompt=system_prompt,
            description=description,
            model=model,
            provider=provider,
            tools=tools or [],
            fallback_models=fallback_models or [],
        )
        self._registry.register(profile)
        self._registry.save_to_yaml(self._agents_yaml)
        return profile

    # -- channels -----------------------------------------------------------

    def list_channels(self) -> list[Channel]:
        return self._store.list_channels()

    def create_channel(self, name: str, members: list[str]) -> Channel:
        # Validate member handles
        for handle in members:
            try:
                self._registry.get(handle)
            except KeyError:
                raise AgentNotFoundError(
                    f"Agent '{handle}' not found"
                ) from None

        ch = self._store.create(name)
        for handle in members:
            try:
                self._store.add_member(ch.id, handle)
            except Exception:
                # Membership already exists — non-fatal
                pass
        return ch

    def list_members(self, channel_id: str) -> list[str]:
        if not self._channel_exists(channel_id):
            raise ChannelNotFound(f"Channel '{channel_id}' not found")
        return self._store.members(channel_id)

    # -- messages -----------------------------------------------------------

    def history(self, channel_id: str, limit: int = 50) -> list:
        if not self._channel_exists(channel_id):
            raise ChannelNotFound(f"Channel '{channel_id}' not found")
        # Clamp limit
        limit = max(1, min(limit, 200))
        return self._store.history(channel_id, limit=limit)

    def post_and_dispatch(
        self,
        channel_id: str,
        author_handle: str,
        body: str,
        dispatch: bool = True,
    ) -> PostMessageResult:
        if not self._channel_exists(channel_id):
            raise ChannelNotFound(f"Channel '{channel_id}' not found")

        # Post user message
        try:
            user_msg = self._store.post(channel_id, author_handle, body)
        except Exception as exc:
            # Author not in channel or channel not found
            if "not a member" in str(exc).lower():
                raise VectorValidationError(
                    f"Author '{author_handle}' is not a member of channel"
                ) from exc
            raise

        all_messages = [user_msg]
        dispatch_result = None

        if dispatch:
            dispatch_result = self._dispatcher.dispatch(
                channel_id,
                author_handle,
                body,
            )
            # Collect agent responses from history
            history = self._store.history(channel_id, limit=50)
            for msg in history:
                if msg.author_handle != author_handle:
                    # Agent message — add if not already in list
                    if not any(m.id == msg.id for m in all_messages):
                        all_messages.append(msg)

        return PostMessageResult(
            message=user_msg,
            dispatch=dispatch_result,
            messages=all_messages,
        )

    # -- lifecycle ----------------------------------------------------------

    def close(self) -> None:
        self._store.close()

    # -- helpers ------------------------------------------------------------

    def _channel_exists(self, channel_id: str) -> bool:
        """Check if a channel exists by querying the channels table directly."""
        row = self._store._conn.execute(
            "SELECT 1 FROM channels WHERE id = ?", (channel_id,)
        ).fetchone()
        return row is not None

    @property
    def health_storage(self) -> str:
        if ":memory:" in self._db_path:
            return "memory"
        return "sqlite"
