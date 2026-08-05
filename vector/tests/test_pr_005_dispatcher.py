"""Contract tests for PR-005 — Channel Dispatcher.

Each test corresponds to one AC in
docs/roadmap/prs/PR-005-channel-dispatcher.md and carries the matching
``@pytest.mark.ac_vec_005_N`` marker.

All tests use a FakeDelegate (no real LLM) and an in-memory SQLite
ChannelStore.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional

import pytest

from vector.profile import AgentProfile, AgentRegistry
from vector.channel import ChannelStore
from vector.runtime import AgentRuntime
from vector.dispatcher import (
    Dispatcher,
    DispatchEntry,
    DispatchResult,
    RecursionLimitExceeded,
)


# ---------------------------------------------------------------------------
# Fake delegate
# ---------------------------------------------------------------------------


@dataclass
class FakeDelegate:
    """A fake delegate for AgentRuntime.

    ``responses`` is a list of JSON strings returned per call in order.
    Each should be ``{"results": [{"status": "ok", "output": ...}]}``.
    """

    responses: list[str] = field(default_factory=list)
    calls: list[dict] = field(default_factory=list)

    def __call__(
        self,
        *,
        goal: str,
        context: Optional[str] = None,
        role: str = "leaf",
        max_iterations: Optional[int] = None,
        model: Optional[str] = None,
        provider: Optional[str] = None,
        tools: Optional[tuple] = None,
    ) -> str:
        self.calls.append({
            "goal": goal,
            "model": model,
        })
        idx = len(self.calls) - 1
        if idx < len(self.responses):
            return self.responses[idx]
        return json.dumps({"results": [{"status": "ok", "output": "ok"}]})


def _ok(output: str) -> str:
    """Helper: build a JSON ok response string."""
    return json.dumps({"results": [{"status": "ok", "output": output}]})


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def registry() -> AgentRegistry:
    reg = AgentRegistry()
    reg.register(AgentProfile(
        handle="gandalf", system_prompt="You are Gandalf.",
        model="anthropic/claude-sonnet-4.5",
    ))
    reg.register(AgentProfile(
        handle="sre", system_prompt="You are an SRE.",
        model="gpt-4o",
    ))
    return reg


@pytest.fixture
def store(registry: AgentRegistry) -> ChannelStore:
    s = ChannelStore(":memory:", registry=registry)
    yield s
    s.close()


@pytest.fixture
def channel(store: ChannelStore) -> str:
    """Create a channel with gandalf + sre as members. Returns channel_id."""
    ch = store.create("dev-room")
    store.add_member(ch.id, "gandalf")
    store.add_member(ch.id, "sre")
    return ch.id


def _make_dispatcher(
    store: ChannelStore,
    registry: AgentRegistry,
    responses: list[str],
) -> tuple[Dispatcher, FakeDelegate]:
    delegate = FakeDelegate(responses=responses)
    rt = AgentRuntime(delegate)
    disp = Dispatcher(store, rt, registry)
    return disp, delegate


# ---------------------------------------------------------------------------
# AC-VEC-005-1 — @gandalf hi → one response by gandalf
# ---------------------------------------------------------------------------


@pytest.mark.ac_vec_005_1
def test_ac_vec_005_1_mention_produces_response(
    store: ChannelStore, registry: AgentRegistry, channel: str,
):
    """Posting ``@gandalf hi`` to a channel containing ``gandalf`` results
    in one response message authored by ``gandalf``."""
    disp, _ = _make_dispatcher(store, registry, [_ok("hello from gandalf")])
    result = disp.dispatch(channel, "user", "@gandalf hi")
    assert len(result.entries) == 1
    assert result.entries[0].handle == "gandalf"
    assert result.entries[0].status == "ok"
    assert result.entries[0].response == "hello from gandalf"


# ---------------------------------------------------------------------------
# AC-VEC-005-2 — @stranger (non-member) → zero responses
# ---------------------------------------------------------------------------


@pytest.mark.ac_vec_005_2
def test_ac_vec_005_2_non_member_ignored(
    store: ChannelStore, registry: AgentRegistry, channel: str,
):
    """Posting ``@stranger hi`` to a channel where ``stranger`` is NOT a
    member results in zero response messages."""
    disp, _ = _make_dispatcher(store, registry, [_ok("should not happen")])
    result = disp.dispatch(channel, "user", "@stranger hi")
    assert len(result.entries) == 0


# ---------------------------------------------------------------------------
# AC-VEC-005-3 — self-mention ignored
# ---------------------------------------------------------------------------


@pytest.mark.ac_vec_005_3
def test_ac_vec_005_3_self_mention_ignored(
    store: ChannelStore, registry: AgentRegistry, channel: str,
):
    """When ``gandalf`` posts ``@gandalf self``, no new message is produced
    (self-mention ignored)."""
    disp, _ = _make_dispatcher(store, registry, [_ok("should not happen")])
    result = disp.dispatch(channel, "gandalf", "@gandalf self")
    assert len(result.entries) == 0


# ---------------------------------------------------------------------------
# AC-VEC-005-4 — cycle a→b→a→b→a stops at depth 3
# ---------------------------------------------------------------------------


@pytest.mark.ac_vec_005_4
def test_ac_vec_005_4_recursion_cap(
    store: ChannelStore, registry: AgentRegistry,
):
    """A cycle ``a → b → a → b → a`` stops at depth 3 and raises
    ``RecursionLimitExceeded``."""
    # Each agent's response always mentions the other, creating a cycle.
    responses = [
        _ok("hey @sre"),        # gandalf → mentions sre    (depth 0)
        _ok("hey @gandalf"),    # sre → mentions gandalf     (depth 1)
        _ok("hey @sre"),        # gandalf → mentions sre     (depth 1)
        _ok("hey @gandalf"),    # sre → mentions gandalf     (depth 2)
        _ok("hey @sre"),        # gandalf → mentions sre     (depth 2)
        _ok("hey @gandalf"),    # sre → mentions gandalf     (depth 3)
        _ok("hey @sre"),        # gandalf → mentions sre     (depth 3)
    ]
    disp, _ = _make_dispatcher(store, registry, responses)
    ch = store.create("cycle-room")
    store.add_member(ch.id, "gandalf")
    store.add_member(ch.id, "sre")

    with pytest.raises(RecursionLimitExceeded):
        disp.dispatch(ch.id, "user", "@gandalf start")


# ---------------------------------------------------------------------------
# AC-VEC-005-5 — history contains original + response in order
# ---------------------------------------------------------------------------


@pytest.mark.ac_vec_005_5
def test_ac_vec_005_5_history_after_dispatch(
    store: ChannelStore, registry: AgentRegistry, channel: str,
):
    """After dispatch, ``ChannelStore.history(channel)`` contains the
    original message AND the agent's response, in order."""
    # Register and add "user" as a channel member so it can post.
    registry.register(AgentProfile(
        handle="user", system_prompt="You are a user.", model="gpt-4o",
    ))
    store.add_member(channel, "user")
    # Post the original message first.
    store.post(channel, "user", "@gandalf hi")
    # Now dispatch it.
    disp, _ = _make_dispatcher(store, registry, [_ok("gandalf reply")])
    result = disp.dispatch(channel, "user", "@gandalf hi")
    assert len(result.entries) == 1

    history = store.history(channel)
    # First message = original user message, second = gandalf's response.
    assert len(history) >= 2
    assert history[0].author_handle == "user"
    assert "@gandalf hi" in history[0].body
    assert history[1].author_handle == "gandalf"
    assert history[1].body == "gandalf reply"


# ---------------------------------------------------------------------------
# AC-VEC-005-6 — sequential: a runs first, b sees a's response
# ---------------------------------------------------------------------------


@pytest.mark.ac_vec_005_6
def test_ac_vec_005_6_sequential_order(
    store: ChannelStore, registry: AgentRegistry, channel: str,
):
    """When ``@gandalf @sre`` is posted, ``gandalf`` runs first and its
    response is visible to ``sre`` via ``ChannelStore.history`` before
    ``sre`` runs.

    We verify this by having the fake delegate check channel history at
    each call and recording what it sees.
    """
    seen_history: list[list[str]] = []

    class SequencingDelegate:
        def __init__(self):
            self._call_count = 0

        def __call__(self, *, goal, context=None, role="leaf",
                     max_iterations=None, model=None, provider=None, tools=None):
            # Record what the channel history looks like at call time.
            msgs = store.history(channel, limit=50)
            seen_history.append([m.body for m in msgs])
            self._call_count += 1
            if self._call_count == 1:
                return _ok("gandalf says hi")       # no @mention → no recursion
            return _ok("sre saw gandalf")

    delegate = SequencingDelegate()
    rt = AgentRuntime(delegate)
    disp = Dispatcher(store, rt, registry)

    result = disp.dispatch(channel, "user", "@gandalf @sre hello")

    assert len(result.entries) == 2
    assert result.entries[0].handle == "gandalf"
    assert result.entries[1].handle == "sre"

    # Before gandalf ran, history should NOT contain gandalf's response.
    assert len(seen_history) >= 2
    gandalf_saw = seen_history[0]
    sre_saw = seen_history[1]
    assert not any("gandalf says hi" in m for m in gandalf_saw), \
        "gandalf should not see its own response before running"
    assert any("gandalf says hi" in m for m in sre_saw), \
        f"sre should see gandalf's response before running. Saw: {sre_saw}"


# ---------------------------------------------------------------------------
# Invariant guards
# ---------------------------------------------------------------------------


def test_dispatch_returns_dispatch_result(
    store: ChannelStore, registry: AgentRegistry, channel: str,
):
    """dispatch() returns a DispatchResult with DispatchEntry items."""
    disp, _ = _make_dispatcher(store, registry, [_ok("ok")])
    result = disp.dispatch(channel, "user", "@gandalf hi")
    assert isinstance(result, DispatchResult)
    assert all(isinstance(e, DispatchEntry) for e in result.entries)


def test_no_mentions_no_responses(
    store: ChannelStore, registry: AgentRegistry, channel: str,
):
    """A message with no @mentions produces zero entries."""
    disp, _ = _make_dispatcher(store, registry, [_ok("nope")])
    result = disp.dispatch(channel, "user", "just a plain message")
    assert len(result.entries) == 0


def test_multiple_mentions_all_processed(
    store: ChannelStore, registry: AgentRegistry, channel: str,
):
    """@gandalf @sre both get processed (both are members)."""
    disp, _ = _make_dispatcher(
        store, registry,
        [_ok("g resp"), _ok("s resp")],
    )
    result = disp.dispatch(channel, "user", "@gandalf @sre hello")
    assert len(result.entries) == 2
    handles = [e.handle for e in result.entries]
    assert "gandalf" in handles
    assert "sre" in handles
