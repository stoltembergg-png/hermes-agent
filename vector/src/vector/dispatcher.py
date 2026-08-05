"""Channel dispatcher — inter-agent conversation engine.

Implements PR-005 of the vector roadmap
(docs/roadmap/prs/PR-005-channel-dispatcher.md).

The dispatcher is the heart of vector.  Given a new message in a
channel, it:

1. Extracts ``@mentions`` via the parser from PR-002.
2. For each mentioned agent (in order of appearance), runs the
   ``AgentRuntime`` from PR-004 with the message + channel context.
3. Appends the agent's response as a new message authored by that
   agent's handle.
4. If the agent's response itself contains ``@mentions``, recurses
   (depth-limited to ``MAX_DEPTH = 3``).

Agents run **sequentially** so each can see earlier replies in the
same dispatch cycle.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .channel import ChannelStore
from .mention import extract_mentions
from .profile import AgentRegistry
from .runtime import AgentRuntime, RunResult


MAX_DEPTH = 3


class RecursionLimitExceeded(Exception):
    """Raised when dispatch recursion exceeds MAX_DEPTH."""


@dataclass(frozen=True)
class DispatchEntry:
    """One agent's response within a dispatch cycle."""

    handle: str
    depth: int
    message: str
    response: str
    status: str = "ok"  # "ok" | "error" | "timeout"


@dataclass
class DispatchResult:
    """The outcome of a ``Dispatcher.dispatch`` call."""

    entries: list[DispatchEntry] = field(default_factory=list)
    recursion_exceeded: bool = False
    error: Optional[str] = None

    @property
    def posted_responses(self) -> list[DispatchEntry]:
        """Only entries whose response was actually posted to the channel."""
        return [e for e in self.entries if e.status == "ok"]


class Dispatcher:
    """Dispatches ``@mentions`` in a channel to the right agents.

    Parameters
    ----------
    store
        The ``ChannelStore`` used for message persistence and history.
    runtime
        The ``AgentRuntime`` used to run agent profiles.
    registry
        The ``AgentRegistry`` for looking up agent profiles by handle.
    max_depth
        Maximum recursion depth for nested mentions (default 3).
    """

    def __init__(
        self,
        store: ChannelStore,
        runtime: AgentRuntime,
        registry: AgentRegistry,
        *,
        max_depth: int = MAX_DEPTH,
    ) -> None:
        self._store = store
        self._runtime = runtime
        self._registry = registry
        self._max_depth = max_depth

    def dispatch(
        self,
        channel_id: str,
        author_handle: str,
        message: str,
        *,
        _depth: int = 0,
    ) -> DispatchResult:
        """Process ``message`` by ``author_handle`` in ``channel_id``.

        Returns a ``DispatchResult`` listing every response posted.

        Raises ``RecursionLimitExceeded`` if recursion exceeds
        ``max_depth``.
        """
        if _depth > self._max_depth:
            raise RecursionLimitExceeded(
                f"dispatch recursion exceeded max_depth={self._max_depth}"
            )

        result = DispatchResult()

        # --- get channel members to validate mentions ---
        members = set(self._store.members(channel_id))

        # --- extract mentions from the message ---
        mentions = extract_mentions(message)

        # --- process each mention sequentially ---
        for handle in mentions:
            # REQ-VEC-005-2: only invoke agents that are channel members.
            if handle not in members:
                continue

            # REQ-VEC-005-3: agents must not reply to themselves.
            if handle == author_handle:
                continue

            # The agent must be registered.
            profile = self._registry.get(handle)
            if profile is None:
                continue

            # Build context: recent channel history for the agent to see.
            history = self._store.history(channel_id, limit=20)
            context_parts = []
            for msg in history:
                context_parts.append(f"[{msg.author_handle}] {msg.body}")
            context_str = "\n".join(context_parts) if context_parts else ""

            # Run the agent.
            run_result = self._runtime.run(
                profile,
                message,
                context=context_str or None,
                timeout=300,
            )

            # Persist the response via ChannelStore.post().
            if run_result.output:
                self._store.post(channel_id, handle, run_result.output)

            entry = DispatchEntry(
                handle=handle,
                depth=_depth,
                message=message,
                response=run_result.output,
                status=run_result.status,
            )
            result.entries.append(entry)

            # REQ-VEC-005-5: check for nested mentions in the response.
            if run_result.status == "ok" and run_result.output:
                nested_mentions = extract_mentions(run_result.output)
                if nested_mentions:
                    # Recurse with the agent's response as the new message.
                    nested_result = self.dispatch(
                        channel_id,
                        handle,  # the responding agent is now the "author"
                        run_result.output,
                        _depth=_depth + 1,
                    )
                    result.entries.extend(nested_result.entries)
                    if nested_result.recursion_exceeded:
                        result.recursion_exceeded = True
                        break  # Stop processing further mentions.

        return result
