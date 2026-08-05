"""Contract tests for PR-003 — Channel Store (SQLite).

Each test corresponds to one AC in
docs/roadmap/prs/PR-003-channel-store.md and carries the matching
``@pytest.mark.ac_vec_003_N`` marker.
"""

from __future__ import annotations

import logging

import pytest

from vector.profile import AgentProfile, AgentRegistry
from vector.channel import (
    Channel,
    ChannelStore,
    ChannelType,
    ChannelVisibility,
    ChannelTooLargeError,
    DmChannelFullError,
    DuplicateMembershipError,
    NotAMemberError,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def registry() -> AgentRegistry:
    reg = AgentRegistry()
    reg.register(AgentProfile(handle="gandalf", system_prompt="You are Gandalf.", model="gpt-4o"))
    reg.register(AgentProfile(handle="frodo", system_prompt="You are Frodo.", model="gpt-4o"))
    reg.register(AgentProfile(handle="sre", system_prompt="You are an SRE.", model="gpt-4o"))
    return reg


@pytest.fixture
def store(registry: AgentRegistry) -> ChannelStore:
    s = ChannelStore(":memory:", registry=registry)
    yield s
    s.close()


@pytest.fixture
def channel(store: ChannelStore) -> Channel:
    return store.create("dev-room")


# ---------------------------------------------------------------------------
# AC-VEC-003-1 — create() round-trips
# ---------------------------------------------------------------------------


@pytest.mark.ac_vec_003_1
def test_ac_vec_003_1_create_round_trip(store: ChannelStore):
    """`create(Channel(name="dev-room"))` round-trips: a fresh `get("dev-room")`
    returns an equal object."""
    ch = store.create("dev-room")
    fetched = store.get("dev-room")
    assert fetched == ch


# ---------------------------------------------------------------------------
# AC-VEC-003-2 — DuplicateMembershipError
# ---------------------------------------------------------------------------


@pytest.mark.ac_vec_003_2
def test_ac_vec_003_2_duplicate_membership(store: ChannelStore, channel: Channel):
    """`add_member(c, "gandalf")` raises `DuplicateMembershipError` if already
    a member."""
    store.add_member(channel.id, "gandalf")
    with pytest.raises(DuplicateMembershipError):
        store.add_member(channel.id, "gandalf")


# ---------------------------------------------------------------------------
# AC-VEC-003-3 — NotAMemberError for unregistered handle
# ---------------------------------------------------------------------------


@pytest.mark.ac_vec_003_3
def test_ac_vec_003_3_unregistered_handle(store: ChannelStore, channel: Channel):
    """`add_member(c, "ghost")` raises `NotAMemberError` if no profile `ghost`
    is registered."""
    with pytest.raises(NotAMemberError):
        store.add_member(channel.id, "ghost")


# ---------------------------------------------------------------------------
# AC-VEC-003-4 — post() extracts mentions
# ---------------------------------------------------------------------------


@pytest.mark.ac_vec_003_4
def test_ac_vec_003_4_post_extracts_mentions(store: ChannelStore, channel: Channel):
    """`post(c, "you", "@gandalf please review")` produces a `Message` with
    `mentions == ["gandalf"]`."""
    # Register author as agent and add both to channel
    store.registry.register(AgentProfile(handle="you", system_prompt="You are you.", model="gpt-4o"))
    store.add_member(channel.id, "gandalf")
    store.add_member(channel.id, "you")
    msg = store.post(channel.id, "you", "@gandalf please review")
    assert msg.mentions == ["gandalf"]


# ---------------------------------------------------------------------------
# AC-VEC-003-5 — history returns oldest first
# ---------------------------------------------------------------------------


@pytest.mark.ac_vec_003_5
def test_ac_vec_003_5_history_chronological(store: ChannelStore, channel: Channel):
    """`history(c)` after three posts returns exactly those three, oldest
    first."""
    store.registry.register(AgentProfile(handle="alice", system_prompt="You are alice.", model="gpt-4o"))
    store.registry.register(AgentProfile(handle="bob", system_prompt="You are bob.", model="gpt-4o"))
    store.add_member(channel.id, "alice")
    store.add_member(channel.id, "bob")
    m1 = store.post(channel.id, "alice", "first")
    m2 = store.post(channel.id, "bob", "second")
    m3 = store.post(channel.id, "alice", "third")
    history = store.history(channel.id)
    assert len(history) == 3
    assert [m.id for m in history] == [m1.id, m2.id, m3.id]


# ---------------------------------------------------------------------------
# AC-VEC-003-6 — search via FTS5
# ---------------------------------------------------------------------------


@pytest.mark.ac_vec_003_6
def test_ac_vec_003_6_search_fts(store: ChannelStore, channel: Channel):
    """`search(c, "review")` returns messages containing the word, ranked by
    FTS5."""
    store.registry.register(AgentProfile(handle="alice", system_prompt="You are alice.", model="gpt-4o"))
    store.add_member(channel.id, "alice")
    store.post(channel.id, "alice", "please review this PR")
    store.post(channel.id, "alice", "nothing related here")
    store.post(channel.id, "alice", "another review needed")
    results = store.search(channel.id, "review")
    assert len(results) == 2
    assert all("review" in m.body for m in results)


# ---------------------------------------------------------------------------
# AC-VEC-003-7 — soft/hard member limits
# ---------------------------------------------------------------------------


@pytest.mark.ac_vec_003_7
def test_ac_vec_003_7_member_limits(store: ChannelStore, registry: AgentRegistry, caplog):
    """`add_member` on a channel with 50 members (soft cap) succeeds and emits a
    warning log; on 200 members (hard cap) raises `ChannelTooLargeError`."""
    # Create a channel with low caps for test feasibility
    ch = store.create("big-room", member_limit_soft=3, member_limit_hard=5)
    # Register 5 agents
    for i in range(5):
        store.registry.register(
            AgentProfile(handle=f"agent{i}", system_prompt=f"You are agent{i}.", model="gpt-4o")
        )
    # Add up to soft cap (3 members)
    for i in range(3):
        store.add_member(ch.id, f"agent{i}")
    # 4th member hits soft cap → warning logged but succeeds
    with caplog.at_level(logging.WARNING, logger="vector.channel"):
        store.add_member(ch.id, "agent3")
    # Verify warning was emitted
    assert any("soft limit" in record.message for record in caplog.records)
    # Verify 4th member was added
    assert "agent3" in store.members(ch.id)
    # Add 5th member (reaches hard cap)
    store.add_member(ch.id, "agent4")
    # 6th member exceeds hard cap → raises
    store.registry.register(AgentProfile(handle="agent5", system_prompt="You are agent5.", model="gpt-4o"))
    with pytest.raises(ChannelTooLargeError):
        store.add_member(ch.id, "agent5")


# ---------------------------------------------------------------------------
# AC-VEC-003-8 — DM cap of exactly 2
# ---------------------------------------------------------------------------


@pytest.mark.ac_vec_003_8
def test_ac_vec_003_8_dm_cap(store: ChannelStore, registry: AgentRegistry):
    """`create(Channel(type="dm"))` accepts exactly 2 members; adding a third
    to a DM channel raises `DmChannelFullError`."""
    dm = store.create("secret-chat", type=ChannelType.DM)
    store.add_member(dm.id, "gandalf")
    store.add_member(dm.id, "frodo")
    # Third member should fail
    with pytest.raises(DmChannelFullError):
        store.add_member(dm.id, "sre")


# ---------------------------------------------------------------------------
# Invariant guards (not AC-tagged)
# ---------------------------------------------------------------------------


def test_store_supports_context_manager(registry: AgentRegistry):
    with ChannelStore(":memory:", registry=registry) as s:
        ch = s.create("temp-room")
        assert s.get(ch.id) == ch
    # After context exit, connection should be closed
    # (Further operations would raise sqlite3.ProgrammingError)


def test_remove_member(store: ChannelStore, channel: Channel):
    store.add_member(channel.id, "gandalf")
    assert "gandalf" in store.members(channel.id)
    store.remove_member(channel.id, "gandalf")
    assert "gandalf" not in store.members(channel.id)


def test_post_requires_membership(store: ChannelStore, channel: Channel):
    """A non-member cannot post to a channel."""
    store.registry.register(AgentProfile(handle="intruder", system_prompt="You are intruder.", model="gpt-4o"))
    from vector.channel import AuthorNotInChannelError
    with pytest.raises(AuthorNotInChannelError):
        store.post(channel.id, "intruder", "hello")


def test_history_before_id(store: ChannelStore, channel: Channel):
    """`history(c, before_id=m2.id)` returns only messages before m2."""
    store.registry.register(AgentProfile(handle="alice", system_prompt="You are alice.", model="gpt-4o"))
    store.add_member(channel.id, "alice")
    m1 = store.post(channel.id, "alice", "first")
    m2 = store.post(channel.id, "alice", "second")
    m3 = store.post(channel.id, "alice", "third")
    # Messages before m2 should be [m1] (only one before m2)
    history = store.history(channel.id, before_id=m2.id)
    assert len(history) == 1
    assert history[0].id == m1.id
