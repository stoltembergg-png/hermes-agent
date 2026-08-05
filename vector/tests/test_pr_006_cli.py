"""Contract tests for PR-006 — Vector CLI.

Each test corresponds to one AC in docs/roadmap/prs/PR-006-cli.md and
carries the matching ``@pytest.mark.ac_vec_006_N`` marker.

Tests use a temp ``HERMES_HOME`` so the CLI persists to a temp dir
that is cleaned up after each test.
"""

from __future__ import annotations

import io
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from vector.cli import main, __version__


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def vector_env(tmp_path: Path, monkeypatch):
    """Set HERMES_HOME to a temp dir so the CLI persists there."""
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    vec_dir = tmp_path / "vector"
    vec_dir.mkdir(parents=True, exist_ok=True)
    return tmp_path


# ---------------------------------------------------------------------------
# AC-VEC-006-1 — agents add succeeds, profile loadable on fresh process
# ---------------------------------------------------------------------------


@pytest.mark.ac_vec_006_1
def test_ac_vec_006_1_agents_add_persists(vector_env: Path):
    """``vector agents add gandalf --system "x"`` succeeds and the
    profile is loadable on a fresh process invocation."""
    rc = main(["agents", "add", "gandalf", "--system", "You are Gandalf."])
    assert rc == 0
    # The YAML file should exist.
    agents_file = vector_env / "vector" / "agents.yaml"
    assert agents_file.exists()
    # Simulate a fresh process by loading the registry from YAML.
    from vector.profile import AgentRegistry
    reg = AgentRegistry.load_from_yaml(agents_file)
    assert reg.has("gandalf")
    assert reg.get("gandalf").system_prompt == "You are Gandalf."


# ---------------------------------------------------------------------------
# AC-VEC-006-2 — agents list prints both handles
# ---------------------------------------------------------------------------


@pytest.mark.ac_vec_006_2
def test_ac_vec_006_2_agents_list_prints_both(vector_env: Path, capsys):
    """``vector agents list`` after adding two profiles prints both."""
    main(["agents", "add", "gandalf", "--system", "G"])
    main(["agents", "add", "frodo", "--system", "F"])
    capsys.readouterr()  # clear
    rc = main(["agents", "list"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "gandalf" in out
    assert "frodo" in out


# ---------------------------------------------------------------------------
# AC-VEC-006-3 — channels add creates channel with members
# ---------------------------------------------------------------------------


@pytest.mark.ac_vec_006_3
def test_ac_vec_006_3_channels_add_with_members(vector_env: Path, capsys):
    """``vector channels add dev-room --members gandalf,reviewer,you``
    creates the channel and lists both members."""
    # First add agents so they're registered.
    main(["agents", "add", "gandalf", "--system", "G"])
    main(["agents", "add", "reviewer", "--system", "R"])
    main(["agents", "add", "you", "--system", "Y"])
    rc = main(["channels", "add", "dev-room", "--members", "gandalf,reviewer,you"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "dev-room" in out
    # Verify via the store directly.
    from vector.profile import AgentRegistry
    from vector.channel import ChannelStore
    reg = AgentRegistry.load_from_yaml(vector_env / "vector" / "agents.yaml")
    store = ChannelStore(str(vector_env / "vector" / "vector.db"), registry=reg)
    channels = store.list_channels()
    assert len(channels) == 1
    assert channels[0].name == "dev-room"
    members = set(store.members(channels[0].id))
    assert "gandalf" in members
    assert "reviewer" in members
    assert "you" in members
    store.close()


# ---------------------------------------------------------------------------
# AC-VEC-006-4 — channels list shows member count
# ---------------------------------------------------------------------------


@pytest.mark.ac_vec_006_4
def test_ac_vec_006_4_channels_list_shows_count(vector_env: Path, capsys):
    """``vector channels list`` shows ``dev-room`` with member count 3."""
    main(["agents", "add", "gandalf", "--system", "G"])
    main(["agents", "add", "reviewer", "--system", "R"])
    main(["agents", "add", "you", "--system", "Y"])
    main(["channels", "add", "dev-room", "--members", "gandalf,reviewer,you"])
    capsys.readouterr()  # clear
    rc = main(["channels", "list"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "dev-room" in out
    assert "3" in out


# ---------------------------------------------------------------------------
# AC-VEC-006-5 — scripted REPL: post @gandalf hi, see response, /quit exits 0
# ---------------------------------------------------------------------------


@pytest.mark.ac_vec_006_5
def test_ac_vec_006_5_scripted_repl(vector_env: Path, capsys):
    """A scripted REPL session: post ``@gandalf hi``, the CLI prints
    ``@gandalf > <response>``, then ``/quit`` exits 0."""
    main(["agents", "add", "gandalf", "--system", "G"])
    main(["channels", "add", "dev-room", "--members", "gandalf"])

    # Mock the Hermes delegate with a stub that returns a fixed response.
    from vector.runtime import AgentRuntime
    import json

    class StubDelegate:
        def __call__(self, *, goal, context=None, role="leaf",
                     max_iterations=None, model=None, provider=None, tools=None):
            return json.dumps({"results": [{"status": "ok", "output": "hello there"}]})

    # Patch the HermesDelegate import inside cli.cmd_chat.
    with patch("vector.cli.HermesDelegate", StubDelegate, create=True):
        # Simulate stdin: "@gandalf hi\n/quit\n"
        inputs = "@gandalf hi\n/quit\n"
        with patch("builtins.input", side_effect=inputs.splitlines(True)):
            rc = main(["chat", "--channel", "dev-room"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "@gandalf >" in out


# ---------------------------------------------------------------------------
# AC-VEC-006-6 — vector --version prints "vector 0.1.0"
# ---------------------------------------------------------------------------


@pytest.mark.ac_vec_006_6
def test_ac_vec_006_6_version(vector_env: Path, capsys):
    """``vector --version`` prints ``vector 0.1.0``."""
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])
    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    assert "vector 0.1.0" in out
    assert __version__ == "0.1.0"


# ---------------------------------------------------------------------------
# AC-VEC-006-7 — adding member to channel with 200 raises ChannelTooLargeError
# ---------------------------------------------------------------------------


@pytest.mark.ac_vec_006_7
def test_ac_vec_006_7_hard_cap_raises(vector_env: Path):
    """Adding a single member to a channel with 200 members raises
    ``ChannelTooLargeError`` and exits non-zero."""
    from vector.profile import AgentRegistry, AgentProfile
    from vector.channel import ChannelStore, ChannelTooLargeError

    # Create a channel with 200 members directly.
    reg = AgentRegistry()
    for i in range(201):
        reg.register(AgentProfile(
            handle=f"agent{i}", system_prompt=f"You are agent{i}.", model="gpt-4o",
        ))
    reg.save_to_yaml(vector_env / "vector" / "agents.yaml")
    store = ChannelStore(str(vector_env / "vector" / "vector.db"), registry=reg)
    ch = store.create("full-room")
    for i in range(200):
        store.add_member(ch.id, f"agent{i}")
    store.close()

    # Now try adding the 201st member via the CLI.
    rc = main(["channels", "add-member", "full-room", "agent200"])
    assert rc != 0


# ---------------------------------------------------------------------------
# AC-VEC-006-8 — add-team atomic: 5 succeed, 6th exceeds cap → rollback all
# ---------------------------------------------------------------------------


@pytest.mark.ac_vec_006_8
def test_ac_vec_006_8_add_team_atomic_rollback(vector_env: Path, capsys):
    """``add-team`` with 5 members succeeds atomically; adding a 6th
    that would exceed the hard cap rolls back all 5 and exits non-zero."""
    from vector.profile import AgentRegistry, AgentProfile
    from vector.channel import ChannelStore

    # Create a channel that already has 196 members (hard cap is 200).
    reg = AgentRegistry()
    for i in range(201):
        reg.register(AgentProfile(
            handle=f"agent{i}", system_prompt=f"You are agent{i}.", model="gpt-4o",
        ))
    reg.save_to_yaml(vector_env / "vector" / "agents.yaml")
    store = ChannelStore(str(vector_env / "vector" / "vector.db"), registry=reg)
    ch = store.create("near-cap-room")
    # Add 196 unique members.
    for i in range(196):
        store.add_member(ch.id, f"agent{i}")
    store.close()

    # Now try add-team with 5 handles — total would be 201 > 200.
    rc = main([
        "channels", "add-team", "near-cap-room",
        "--handles", "agent196,agent197,agent198,agent199,agent200",
    ])
    assert rc != 0

    # Verify none of the 5 add-team handles were actually added (rollback).
    reg2 = AgentRegistry.load_from_yaml(vector_env / "vector" / "agents.yaml")
    store2 = ChannelStore(str(vector_env / "vector" / "vector.db"), registry=reg2)
    channels = store2.list_channels()
    near_cap = [c for c in channels if c.name == "near-cap-room"][0]
    members = set(store2.members(near_cap.id))
    # The 5 add-team handles (agent196..agent200) should NOT be in the channel.
    # The original 196 members (agent0..agent195) should still be there.
    assert len(members) == 196, f"expected 196 members after rollback, got {len(members)}"
    assert "agent196" not in members
    assert "agent197" not in members
    assert "agent198" not in members
    assert "agent199" not in members
    assert "agent200" not in members
    store2.close()


# ---------------------------------------------------------------------------
# Invariant guards
# ---------------------------------------------------------------------------


def test_no_command_prints_help(vector_env: Path, capsys):
    """Running ``vector`` with no subcommand prints help and exits 0."""
    rc = main([])
    assert rc == 0


def test_agents_list_empty(vector_env: Path, capsys):
    """``vector agents list`` with no agents prints 'No agents registered.'."""
    rc = main(["agents", "list"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "No agents" in out


def test_channels_list_empty(vector_env: Path, capsys):
    """``vector channels list`` with no channels prints 'No channels.'."""
    rc = main(["channels", "list"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "No channels" in out
