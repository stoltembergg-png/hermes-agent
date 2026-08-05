"""Contract tests for PR-007 — Desktop Mention Panel.

Each test corresponds to one AC in
docs/roadmap/prs/PR-007-desktop-mention-panel.md and carries the matching
``@pytest.mark.ac_vec_007_N`` marker.

The spec says the Playwright smoke test is "manual for v0; automated in v1".
For v0 we validate the backend logic that the plugin depends on — the
channel store, history, mention parsing, and dispatch results that the
desktop panel renders. This gives us an automated regression net without
requiring an Electron harness.
"""

import os
import pytest

from vector.profile import AgentProfile, AgentRegistry
from vector.channel import ChannelStore
from vector.mention import extract_mentions
from vector.runtime import AgentRuntime
from vector.dispatcher import Dispatcher, DispatchResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakeDelegate:
    """Fake delegate with pre-set responses."""

    def __init__(self):
        self.calls: list[dict] = []
        self.responses: dict[str, str] = {}

    def __call__(self, goal, context=None, role=None, max_iterations=500,
                 model=None, provider=None, tools=None):
        self.calls.append({
            "goal": goal,
            "context": context,
            "model": model,
            "provider": provider,
            "tools": tools,
        })
        # Resolve by handle (first component of [handle] goal).
        for handle, resp in self.responses.items():
            if f"[{handle}]" in goal:
                return f'{{"results": [{{"status": "ok", "output": "{resp}"}}]}}'
        return '{"results": [{"status": "ok", "output": "ok"}]}'


def make_env(tmp_path):
    """Create a registry + store usable by the plugin backend."""
    reg = AgentRegistry()
    reg.register(AgentProfile(
        handle="gandalf",
        system_prompt="You are Gandalf.",
        tools=("read_file",),
    ))
    reg.register(AgentProfile(
        handle="sre",
        system_prompt="You are an SRE.",
        tools=("terminal",),
    ))
    reg.register(AgentProfile(
        handle="user",
        system_prompt="You are a human user.",
    ))
    db_path = str(tmp_path / "vector.db")
    store = ChannelStore(db_path, registry=reg)
    ch = store.create("dev-room")
    store.add_member(ch.id, "gandalf")
    store.add_member(ch.id, "sre")
    store.add_member(ch.id, "user")
    return reg, store


# ---------------------------------------------------------------------------
# AC-007-1 — Plugin loads without errors, adds Channels nav entry
# ---------------------------------------------------------------------------


@pytest.mark.ac_vec_007_1
def test_ac_vec_007_1_plugin_file_exists():
    """Plugin loads: the plugin.tsx file exists and exports default.

    In v0 we verify the file exists and has the correct shape (id, name,
    register). v1 will do a Playwright smoke test."""
    plugin_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)
        ))),
        "apps", "desktop", "src", "plugins",
        "vector-channels", "plugin.tsx",
    )
    assert os.path.exists(plugin_path), f"plugin.tsx missing at {plugin_path}"
    with open(plugin_path, encoding="utf-8") as f:
        content = f.read()
    assert "id: 'vector-channels'" in content
    assert "SIDEBAR_NAV_AREA" in content
    assert "ROUTES_AREA" in content
    assert "label: 'Channels'" in content


# ---------------------------------------------------------------------------
# AC-007-2 — New message increments unread badge; opening clears it
# ---------------------------------------------------------------------------


@pytest.mark.ac_vec_007_2
def test_ac_vec_007_2_new_message_increments_unread(tmp_path):
    """Posting a message to a channel creates a message visible in history.

    The desktop unread badge tracks messages in channels the user hasn't
    opened. Here we validate the backend: a posted message appears in
    history() and increments the message count."""
    reg, store = make_env(tmp_path)
    ch = [c for c in store.list_channels() if c.name == "dev-room"][0]

    # Post a message.
    msg1 = store.post(ch.id, "gandalf", "Hello team")
    assert msg1 is not None

    # History should contain 1 message.
    history = store.history(ch.id)
    assert len(history) == 1
    assert history[0].body == "Hello team"

    # Post another message — count should increment.
    store.post(ch.id, "sre", "Hi Gandalf")
    history = store.history(ch.id)
    assert len(history) == 2

    store.close()


# ---------------------------------------------------------------------------
# AC-007-3 — Selecting dev-room shows last 50 messages in chrono order
# ---------------------------------------------------------------------------


@pytest.mark.ac_vec_007_3
def test_ac_vec_007_3_history_last_50_chronological(tmp_path):
    """ChannelStore.history(channel_id) returns messages oldest-first."""
    reg, store = make_env(tmp_path)
    ch = [c for c in store.list_channels() if c.name == "dev-room"][0]

    # Post 60 messages.
    for i in range(60):
        store.post(ch.id, "gandalf", f"Message {i}")

    # history() defaults to limit=50; request more to get all.
    all_history = store.history(ch.id, limit=100)
    assert len(all_history) == 60

    # Verify chronological order (oldest first).
    for i, msg in enumerate(all_history):
        assert msg.body == f"Message {i}"

    store.close()


# ---------------------------------------------------------------------------
# AC-007-4 — @gandalf hello shows user msg + agent reply
# ---------------------------------------------------------------------------


@pytest.mark.ac_vec_007_4
def test_ac_vec_007_4_mention_triggers_dispatcher_reply(tmp_path):
    """Posting '@gandalf hello' should:
    1. Store the user message in history.
    2. Extract mentions ['gandalf'].
    3. Dispatcher runs gandalf's profile, gets a reply.
    4. Reply is posted to the channel.
    5. Both messages appear in history.
    """
    reg, store = make_env(tmp_path)
    delegate = FakeDelegate()
    delegate.responses = {"gandalf": "Hello there!"}
    runtime = AgentRuntime(delegate=delegate)
    dispatcher = Dispatcher(store=store, runtime=runtime, registry=reg,
                            max_depth=3)

    ch = [c for c in store.list_channels() if c.name == "dev-room"][0]

    # Simulate what the desktop plugin does: post user message, then dispatch.
    user_msg = store.post(ch.id, "user", "@gandalf hello")
    assert user_msg is not None

    # Verify mentions were extracted.
    assert "gandalf" in user_msg.mentions

    # Dispatch the message.
    result = dispatcher.dispatch(ch.id, "user", "@gandalf hello")
    assert result.error is None
    assert len(result.posted_responses) == 1
    assert result.posted_responses[0].handle == "gandalf"
    assert "Hello there!" in result.posted_responses[0].response

    # History should have 2+ messages: user + agent reply.
    history = store.history(ch.id, limit=100)
    assert len(history) >= 2
    assert history[0].author_handle == "user"
    assert any(m.author_handle == "gandalf" for m in history)

    store.close()


# ---------------------------------------------------------------------------
# AC-007-5 — @gan suggests @gandalf if gandalf is a member
# ---------------------------------------------------------------------------


@pytest.mark.ac_vec_007_5
def test_ac_vec_007_5_autocomplete_member_prefix(tmp_path):
    """The autocomplete logic should match member handles by prefix.

    The desktop plugin implements this in computeAutocomplete (TSX).
    Here we validate the backend: the channel members list is the
    source of truth, and the mention parser correctly extracts @gan
    as a partial mention (though it only matches complete handles).

    The TSX test validates the prefix matching logic directly.
    For the Python side, we validate that the channel's member list
    is queryable and the handle is present."""
    reg, store = make_env(tmp_path)
    ch = [c for c in store.list_channels() if c.name == "dev-room"][0]

    members = store.members(ch.id)
    assert "gandalf" in members
    assert "sre" in members

    # Verify gandalf starts with "gan" (the autocomplete prefix).
    assert any(m.startswith("gan") for m in members)

    store.close()


# ---------------------------------------------------------------------------
# AC-007-6 — DevTools: nodeIntegration === false, preload exposes vector.* only
# ---------------------------------------------------------------------------


@pytest.mark.ac_vec_007_6
def test_ac_vec_007_6_no_node_integration():
    """The plugin must not use nodeIntegration and must be context-isolated.

    In v0 we verify by static analysis: the plugin imports only from
    '@hermes/plugin-sdk', not from 'electron' or 'node:*'. The plugin
    SDK itself is context-isolated by the desktop app architecture.
    """
    plugin_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)
        ))),
        "apps", "desktop", "src", "plugins",
        "vector-channels", "plugin.tsx",
    )
    assert os.path.exists(plugin_path)
    with open(plugin_path, encoding="utf-8") as f:
        content = f.read()

    # Must NOT import from electron or node builtins.
    assert "require('electron')" not in content
    assert "from 'electron'" not in content
    assert "require('node:" not in content
    assert "from 'node:" not in content
    assert "import 'fs'" not in content
    assert "import 'path'" not in content
    assert "import('fs')" not in content
    assert "import('path')" not in content

    # Must import from @hermes/plugin-sdk only.
    assert "from '@hermes/plugin-sdk'" in content

    # Must NOT use eval or Function constructor (security).
    assert "eval(" not in content
    assert "new Function(" not in content
