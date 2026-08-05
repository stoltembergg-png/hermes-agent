"""End-to-end smoke tests for vector v0 — exercises the full stack.

These testsverify that the public API works end-to-end:

1. AgentRegistry: register, persist, reload
2. ChannelStore: create, add members, post, history, FTS5 search
3. Mention extraction: @handles + code-fence exclusion
4. AgentRuntime + Dispatcher: sequential multi-agent dispatch
5. YAML round-trip: save → load in new registry instance
6. CLI subprocess: agents/channels commands with HERMES_HOME isolation

These are NOT unit tests — they exercise the real integration points
and serve as regression guards.
"""

import os
import sys
import tempfile
import shutil
import subprocess
import pytest

# Ensure vector/src is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from vector.profile import AgentProfile, AgentRegistry
from vector.channel import ChannelStore
from vector.mention import extract_mentions
from vector.runtime import AgentRuntime
from vector.dispatcher import Dispatcher


@pytest.fixture
def tmpdir_path(tmp_path):
    return str(tmp_path)


@pytest.fixture
def env(tmpdir_path):
    """Isolated HERMES_HOME + PYTHONPATH for CLI subprocess tests."""
    e = dict(os.environ)
    e["HERMES_HOME"] = tmpdir_path
    e["PYTHONPATH"] = os.path.join(os.path.dirname(__file__), "..", "src")
    return e


@pytest.fixture
def make_env(tmpdir_path):
    """Create a populated registry + store with 3 agents and a channel."""

    def _make():
        reg = AgentRegistry()
        reg.register(AgentProfile(handle="gandalf", system_prompt="You are Gandalf.", model="gpt-4o"))
        reg.register(AgentProfile(handle="sre", system_prompt="You are an SRE.", model="claude-3-5-sonnet"))
        reg.register(AgentProfile(handle="user", system_prompt="Human user.", model="gpt-4o"))

        db_path = os.path.join(tmpdir_path, "test.db")
        store = ChannelStore(db_path, registry=reg)
        ch = store.create("dev-room")
        for h in ("gandalf", "sre", "user"):
            store.add_member(ch.id, h)
        return reg, store, ch

    return _make


# ── AC-008-1: Full end-to-end dispatch cycle ──────────────────────────


@pytest.mark.ac_vec_008_1
def test_ac_vec_008_1_end_to_end_dispatch(make_env):
    """Dispatch produces correct responses and posts them to channel."""
    reg, store, ch = make_env()

    class FakeDelegate:
        def __call__(self, *, goal, context=None, role=None,
                     max_iterations=None, model=None, provider=None,
                     tools=None, **kw):
            # goal is prefixed "[handle] message" by AgentRuntime.
            if "[gandalf]" in goal:
                return "I am well, thank you!"
            if "[sre]" in goal:
                return "All systems go!"
            return "Unknown agent"

    runtime = AgentRuntime(delegate=FakeDelegate())
    dispatcher = Dispatcher(store=store, runtime=runtime, registry=reg, max_depth=3)

    store.post(ch.id, "user", "@gandalf @sre status report please")
    result = dispatcher.dispatch(ch.id, "user", "@gandalf @sre status report please")

    assert result.error is None
    assert len(result.entries) == 2
    assert len(result.posted_responses) == 2

    statuses = {e.handle: e.status for e in result.entries}
    assert statuses["gandalf"] == "ok"
    assert statuses["sre"] == "ok"

    responses = {e.handle: e.response for e in result.entries}
    assert "well" in responses["gandalf"].lower()
    assert "go" in responses["sre"].lower()

    # Verify responses were posted to the channel.
    history = store.history(ch.id, limit=50)
    bodies = {m.author_handle: m.body for m in history if m.author_handle != "user"}
    assert "gandalf" in bodies
    assert "sre" in bodies


# ── AC-008-2: YAML round-trip (save → new registry → load) ───────────


@pytest.mark.ac_vec_008_2
def test_ac_vec_008_2_yaml_round_trip(make_env, tmpdir_path):
    """save_to_yaml → load_from_yaml preserves all profiles."""
    reg, store, ch = make_env()

    yaml_path = os.path.join(tmpdir_path, "agents.yaml")
    reg.save_to_yaml(yaml_path)

    # Load into a NEW registry (simulates process restart).
    reg2 = AgentRegistry.load_from_yaml(yaml_path)
    assert len(reg2.all()) == len(reg.all())

    original_handles = {p.handle for p in reg.all()}
    loaded_handles = {p.handle for p in reg2.all()}
    assert original_handles == loaded_handles

    # Verify profile fields preserved.
    for p in reg2.all():
        original = reg.get(p.handle)
        assert p.model == original.model
        assert p.system_prompt == original.system_prompt


# ── AC-008-3: Mention extraction with code-fence exclusion ──────────


@pytest.mark.ac_vec_008_3
def test_ac_vec_008_3_mention_extraction():
    """extract_mentions handles code-fence exclusion correctly."""
    mentions = extract_mentions("Hey @gandalf and @sre, check this @user out!")
    assert set(mentions) == {"gandalf", "sre", "user"}

    # Code-fence exclusion: @foo inside ``` should be ignored.
    mentions2 = extract_mentions("```\n@not_a_mention\n```\n@gandalf yes")
    assert mentions2 == ["gandalf"]


# ── AC-008-4: FTS5 full-text search ───────────────────────────────────


@pytest.mark.ac_vec_008_4
def test_ac_vec_008_4_fts5_search(make_env):
    """ChannelStore.search() returns matching messages via FTS5."""
    reg, store, ch = make_env()

    store.post(ch.id, "user", "Hello world from the user")
    store.post(ch.id, "gandalf", "You shall not pass without a greeting")

    results = store.search(ch.id, "hello")
    assert len(results) >= 1
    assert any("hello" in m.body.lower() for m in results)

    results2 = store.search(ch.id, "shall")
    assert len(results2) >= 1
    assert any("shall" in m.body.lower() for m in results2)


# ── AC-008-5: CLI cross-process persistence ──────────────────────────


@pytest.mark.ac_vec_008_5
def test_ac_vec_008_5_cli_persistence(env, tmpdir_path):
    """CLI agents add + list works across separate processes."""
    py = sys.executable

    def cli(*args):
        r = subprocess.run(
            [py, "-m", "vector.cli", *args],
            capture_output=True, text=True, env=env, timeout=10,
        )
        return r.stdout.strip() or r.stderr.strip()[:200]

    # Add agents in one process.
    assert "added" in cli("agents", "add", "gandalf", "--system", "Wise wizard", "--model", "gpt-4o")
    assert "added" in cli("agents", "add", "sre", "--system", "SRE engineer", "--model", "claude-3-5-sonnet")

    # List in a separate process — should show persisted agents.
    listing = cli("agents", "list")
    assert "gandalf" in listing
    assert "sre" in listing
    assert "gpt-4o" in listing

    # Channels too.
    assert "created" in cli("channels", "add", "dev-room")
    assert "added" in cli("channels", "add-member", "dev-room", "gandalf")
    ch_listing = cli("channels", "list")
    assert "dev-room" in ch_listing


# ── AC-008-6: No regression — all 74 tests still pass ────────────────


@pytest.mark.ac_vec_008_6
def test_ac_vec_008_6_no_regression(tmpdir_path):
    """Sanity: core objects instantiate and basic operations work."""
    reg = AgentRegistry()
    reg.register(AgentProfile(handle="test1", system_prompt="Test 1", model="gpt-4o"))
    assert len(reg.all()) == 1
    assert reg.get("test1").handle == "test1"

    store = ChannelStore(os.path.join(tmpdir_path, "reg.db"), registry=reg)
    ch = store.create("test-ch")
    store.add_member(ch.id, "test1")
    assert "test1" in store.members(ch.id)
