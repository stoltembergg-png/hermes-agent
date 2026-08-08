"""Contract tests for PR-016 — Delete agent + delete channel backend.

Validates the four acceptance criteria from the PR-016 spec:

1. ``DELETE /channels/{channel_id}`` removes a channel from the store.
2. ``DELETE /channels/{channel_id}`` returns ``204 No Content`` on success.
3. ``DELETE /agents/{handle}`` removes an agent from the store.
4. ``DELETE /agents/{handle}`` returns ``204 No Content`` on success.

The tests mount the dashboard ``plugin_api.router`` (the FastAPI router
that the desktop plugin serves under ``/api/plugins/vector-channels``)
on a bare ``FastAPI`` app and exercise it via ``starlette.testclient``
— the same hermetic pattern used by ``test_pr_009`` /
``test_pr_013``. A ``FakeDelegate`` runtime gives deterministic responses
so the suite runs without any provider keys.

Each test carries the matching ``@pytest.mark.ac_vec_016_N`` marker so
the verify-feature.sh collector can map ACs 1:1 to pass/fail results.
"""

from __future__ import annotations

import os
import sys

import pytest

# Ensure vector/src is importable (same pattern as the other vector tests).
sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "src"),
)

# The plugin_api module lives under plugins/vector-channels/dashboard.
_PLUGIN_API_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "plugins",
    "vector-channels", "dashboard",
)
if _PLUGIN_API_DIR not in sys.path:
    sys.path.insert(0, _PLUGIN_API_DIR)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def vector_env(tmp_path):
    """Isolated VectorService with a fake delegate runtime (hermetic)."""
    from vector.service import VectorService
    from vector.runtime import AgentRuntime

    class FakeDelegate:
        def __call__(self, *, goal, context=None, role=None,
                     max_iterations=None, model=None, provider=None,
                     tools=None, **kw):
            return "ok"

    runtime = AgentRuntime(delegate=FakeDelegate())
    db_path = str(tmp_path / "vector.db")
    yaml_path = str(tmp_path / "agents.yaml")
    service = VectorService(
        db_path=db_path,
        agents_yaml=yaml_path,
        runtime=runtime,
    )
    # Pre-register 'human' so channel creation with a human member works.
    service.create_agent(handle="human", system_prompt="Human user")
    yield service
    service.close()


@pytest.fixture
def plugin_client(vector_env):
    """FastAPI TestClient with the dashboard plugin router mounted.

    The dashboard plugin_api uses a module-level ``_service_instance``
    singleton behind ``_get_service()``. We swap it for our test service
    so the router operates on the same hermetic VectorService without
    touching ``$HERMES_HOME``.
    """
    import plugin_api

    plugin_api._service_instance = vector_env

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(plugin_api.router, prefix="/api/plugins/vector-channels")
    yield TestClient(app)

    # Tear down: clear the singleton so later tests get a fresh service.
    plugin_api._service_instance = None


# ---------------------------------------------------------------------------
# AC-VEC-016-1: DELETE /channels/{channel_id} removes the channel from the store
# ---------------------------------------------------------------------------


@pytest.mark.ac_vec_016_1
def test_delete_channel_removes_from_store(plugin_client, vector_env):
    """A channel that existed before DELETE is absent from ``GET /channels``
    and from the underlying ``ChannelStore`` afterwards.
    """
    # Create a channel through the service so we exercise the real path.
    ch = vector_env.create_channel(name="to-delete", members=["human"])

    # Pre-condition: the channel is listed.
    listing = plugin_client.get("/api/plugins/vector-channels/channels")
    assert listing.status_code == 200
    pre_ids = [c["id"] for c in listing.json()["channels"]]
    assert ch.id in pre_ids

    # Act: DELETE the channel.
    resp = plugin_client.delete(f"/api/plugins/vector-channels/channels/{ch.id}")
    assert resp.status_code == 204

    # Post-condition 1: not listed by the API.
    listing2 = plugin_client.get("/api/plugins/vector-channels/channels")
    assert listing2.status_code == 200
    post_ids = [c["id"] for c in listing2.json()["channels"]]
    assert ch.id not in post_ids

    # Post-condition 2: removed from the underlying store too.
    from vector.channel import ChannelNotFoundError

    with pytest.raises(ChannelNotFoundError):
        vector_env._store.get(ch.id)

    # Post-condition 3: memberships + messages rows are gone as well.
    members = vector_env._store._conn.execute(
        "SELECT COUNT(*) FROM memberships WHERE channel_id = ?", (ch.id,)
    ).fetchone()[0]
    messages = vector_env._store._conn.execute(
        "SELECT COUNT(*) FROM messages WHERE channel_id = ?", (ch.id,)
    ).fetchone()[0]
    assert members == 0
    assert messages == 0


# ---------------------------------------------------------------------------
# AC-VEC-016-2: DELETE /channels/{channel_id} returns 204
# ---------------------------------------------------------------------------


@pytest.mark.ac_vec_016_2
def test_delete_channel_returns_204(plugin_client, vector_env):
    """The DELETE channel response carries HTTP 204 with no body."""
    ch = vector_env.create_channel(name="for-204", members=["human"])

    resp = plugin_client.delete(f"/api/plugins/vector-channels/channels/{ch.id}")
    assert resp.status_code == 204
    # 204 responses have no body — Starlette returns b"" content.
    assert resp.content in (b"", None)


# ---------------------------------------------------------------------------
# AC-VEC-016-3: DELETE /agents/{handle} removes the agent from the store
# ---------------------------------------------------------------------------


@pytest.mark.ac_vec_016_3
def test_delete_agent_removes_from_store(plugin_client, vector_env):
    """An agent that existed before DELETE is absent from ``GET /agents``
    and from the underlying ``AgentRegistry`` afterwards.
    """
    # Register an agent through the service.
    vector_env.create_agent(handle="removeme", system_prompt="To be deleted")

    # Pre-condition: the agent is listed.
    listing = plugin_client.get("/api/plugins/vector-channels/agents")
    assert listing.status_code == 200
    pre_handles = [a["handle"] for a in listing.json()["agents"]]
    assert "removeme" in pre_handles

    # Act: DELETE the agent.
    resp = plugin_client.delete("/api/plugins/vector-channels/agents/removeme")
    assert resp.status_code == 204

    # Post-condition 1: not listed by the API.
    listing2 = plugin_client.get("/api/plugins/vector-channels/agents")
    assert listing2.status_code == 200
    post_handles = [a["handle"] for a in listing2.json()["agents"]]
    assert "removeme" not in post_handles

    # Post-condition 2: removed from the registry.
    assert not vector_env._registry.has("removeme")


# ---------------------------------------------------------------------------
# AC-VEC-016-4: DELETE /agents/{handle} returns 204
# ---------------------------------------------------------------------------


@pytest.mark.ac_vec_016_4
def test_delete_agent_returns_204(plugin_client, vector_env):
    """The DELETE agent response carries HTTP 204 with no body."""
    vector_env.create_agent(handle="for-204", system_prompt="To be deleted")

    resp = plugin_client.delete("/api/plugins/vector-channels/agents/for-204")
    assert resp.status_code == 204
    assert resp.content in (b"", None)
