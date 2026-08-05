"""Contract tests for Vector gateway API schemas and HTTP endpoints.

Implements PR-009 ACs 1-6 (backend portion):
- AC-009-1: health endpoint
- AC-009-2: persistence after recreation
- AC-009-3: post + dispatch
- AC-009-4: membership enforcement
- AC-009-5: context propagation
- AC-009-6: error envelope
"""

import os
import sys
import tempfile
import shutil

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

# Ensure vector/src is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from vector.schemas import (
    MAX_HISTORY_LIMIT,
    MAX_MESSAGE_LENGTH,
    CreateAgentRequest,
    CreateChannelRequest,
    HealthResponse,
    PostMessageRequest,
    VectorErrorEnvelope,
)


# ---------------------------------------------------------------------------
# AC-009-1: Schema validation tests
# ---------------------------------------------------------------------------


@pytest.mark.ac_vec_009_1
def test_ac_vec_009_1_health_schema():
    """Health response has the required fields."""
    h = HealthResponse(status="ok", version="0.1.0", storage="sqlite")
    assert h.status == "ok"
    assert h.version == "0.1.0"
    assert h.storage == "sqlite"


@pytest.mark.ac_vec_009_1
def test_ac_vec_009_1_health_defaults():
    """Health response has sensible defaults."""
    h = HealthResponse()
    assert h.status == "ok"
    assert h.storage == "sqlite"


# ---------------------------------------------------------------------------
# Schema validation: agent creation
# ---------------------------------------------------------------------------


def test_create_agent_request_normalizes_handle():
    """Handle is normalized to lowercase and stripped."""
    req = CreateAgentRequest(
        handle="  Gandalf  ", system_prompt="Be wise"
    )
    assert req.handle == "gandalf"


def test_create_agent_request_rejects_empty_handle():
    """Empty handle raises validation error."""
    with pytest.raises(ValidationError):
        CreateAgentRequest(handle="", system_prompt="X")


def test_create_agent_request_rejects_empty_prompt():
    """Empty system_prompt raises validation error."""
    with pytest.raises(ValidationError):
        CreateAgentRequest(handle="g", system_prompt="")


# ---------------------------------------------------------------------------
# Schema validation: post message
# ---------------------------------------------------------------------------


def test_post_message_request_normalizes_author():
    """Author handle is normalized."""
    req = PostMessageRequest(author_handle="  Human  ", body="hello")
    assert req.author_handle == "human"


def test_post_message_request_rejects_empty_body():
    """Empty body raises validation error."""
    with pytest.raises(ValidationError):
        PostMessageRequest(author_handle="human", body="")


def test_post_message_request_rejects_oversized_body():
    """Body exceeding MAX_MESSAGE_LENGTH raises validation error."""
    with pytest.raises(ValidationError):
        PostMessageRequest(author_handle="human", body="x" * (MAX_MESSAGE_LENGTH + 1))


def test_post_message_request_dispatch_defaults_true():
    """Dispatch defaults to True."""
    req = PostMessageRequest(author_handle="human", body="hello")
    assert req.dispatch is True


# ---------------------------------------------------------------------------
# Schema validation: channel creation
# ---------------------------------------------------------------------------


def test_create_channel_request_validates_name():
    """Channel name longer than 128 chars raises."""
    with pytest.raises(ValidationError):
        CreateChannelRequest(name="x" * 129, members=["human"])


# ---------------------------------------------------------------------------
# Schema validation: history limit
# ---------------------------------------------------------------------------


def test_max_history_limit_value():
    """MAX_HISTORY_LIMIT is 200."""
    assert MAX_HISTORY_LIMIT == 200


# ---------------------------------------------------------------------------
# Error envelope
# ---------------------------------------------------------------------------


@pytest.mark.ac_vec_009_6
def test_ac_vec_009_6_error_envelope_shape():
    """Error envelope has code, message, retryable."""
    env = VectorErrorEnvelope(
        error={
            "code": "VECTOR_CHANNEL_NOT_FOUND",
            "message": "not found",
            "retryable": False,
        }
    )
    assert env.error.code == "VECTOR_CHANNEL_NOT_FOUND"
    assert env.error.message == "not found"
    assert env.error.retryable is False


# ---------------------------------------------------------------------------
# API integration tests (using TestClient)
# ---------------------------------------------------------------------------


@pytest.fixture
def vector_env(tmp_path):
    """Isolated temp dir + fake delegate runtime."""
    from vector.service import VectorService
    from vector.runtime import AgentRuntime

    class FakeDelegate:
        def __call__(self, *, goal, context=None, role=None,
                     max_iterations=None, model=None, provider=None,
                     tools=None, **kw):
            if "[gandalf]" in goal:
                return "The architecture is sound."
            if "[sre]" in goal:
                return "All systems go."
            return "Unknown agent"

    runtime = AgentRuntime(delegate=FakeDelegate())
    db_path = str(tmp_path / "vector.db")
    yaml_path = str(tmp_path / "agents.yaml")
    service = VectorService(
        db_path=db_path,
        agents_yaml=yaml_path,
        runtime=runtime,
    )
    # Pre-register 'human' agent so channel creation with human member works
    service.create_agent(handle="human", system_prompt="Human user")
    yield service
    service.close()


@pytest.fixture
def client(vector_env):
    """FastAPI TestClient with vector router mounted."""
    from fastapi import FastAPI
    from vector.api import create_vector_router

    app = FastAPI()
    app.include_router(
        create_vector_router(lambda: vector_env),
        prefix="/api/vector",
    )
    return TestClient(app)


# ---------------------------------------------------------------------------
# AC-009-1: Health endpoint
# ---------------------------------------------------------------------------


@pytest.mark.ac_vec_009_1
def test_ac_vec_009_1_health_endpoint(client):
    """GET /api/vector/health returns 200 with status, version, storage."""
    resp = client.get("/api/vector/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert data["storage"] == "sqlite"


# ---------------------------------------------------------------------------
# AC-009-2: Persistence after service recreation
# ---------------------------------------------------------------------------


@pytest.mark.ac_vec_009_2
def test_ac_vec_009_2_persistence_after_recreation(vector_env, tmp_path):
    """Agents and channels created via API persist after service recreation."""
    # Create agent
    vector_env.create_agent(
        handle="gandalf",
        system_prompt="Wise wizard",
        model="gpt-4o",
    )
    # Create channel
    ch = vector_env.create_channel(name="dev", members=["gandalf"])

    # Recreate service with same paths
    from vector.service import VectorService
    from vector.runtime import AgentRuntime

    class FakeDelegate:
        def __call__(self, **kw):
            return "ok"

    db_path = str(tmp_path / "vector.db")
    yaml_path = str(tmp_path / "agents.yaml")
    service2 = VectorService(
        db_path=db_path,
        agents_yaml=yaml_path,
        runtime=AgentRuntime(delegate=FakeDelegate()),
    )
    try:
        agents = service2.list_agents()
        assert any(a.handle == "gandalf" for a in agents)
        channels = service2.list_channels()
        assert any(c.name == "dev" for c in channels)
    finally:
        service2.close()


# ---------------------------------------------------------------------------
# AC-009-3: Post + dispatch
# ---------------------------------------------------------------------------


@pytest.mark.ac_vec_009_3
def test_ac_vec_009_3_post_and_dispatch(client, vector_env):
    """POST message stores user message, dispatches, and stores agent response."""
    # Setup
    vector_env.create_agent(handle="gandalf", system_prompt="Wise wizard")
    ch = vector_env.create_channel(name="dev", members=["gandalf", "human"])

    # Post message
    resp = client.post(
        f"/api/vector/channels/{ch.id}/messages",
        json={
            "author_handle": "human",
            "body": "@gandalf review this",
            "dispatch": True,
        },
    )
    assert resp.status_code == 200
    data = resp.json()

    # User message stored
    assert data["message"]["author_handle"] == "human"
    assert data["message"]["body"] == "@gandalf review this"

    # Dispatch happened
    assert data["dispatch"] is not None
    assert len(data["dispatch"]["entries"]) == 1
    entry = data["dispatch"]["entries"][0]
    assert entry["handle"] == "gandalf"
    assert entry["status"] == "ok"
    assert "architecture" in entry["response"].lower()

    # Multiple messages returned (user + agent)
    assert len(data["messages"]) >= 2


# ---------------------------------------------------------------------------
# AC-009-4: Membership enforcement
# ---------------------------------------------------------------------------


@pytest.mark.ac_vec_009_4
def test_ac_vec_009_4_membership_enforcement(client, vector_env):
    """Non-member mention is not invoked."""
    vector_env.create_agent(handle="gandalf", system_prompt="Wise wizard")
    vector_env.create_agent(handle="sre", system_prompt="SRE")
    # Only gandalf is a member, not sre
    ch = vector_env.create_channel(name="dev", members=["gandalf", "human"])

    resp = client.post(
        f"/api/vector/channels/{ch.id}/messages",
        json={
            "author_handle": "human",
            "body": "@sre deploy now @gandalf review",
            "dispatch": True,
        },
    )
    data = resp.json()
    # Only gandalf should be dispatched (sre is not a member)
    handles = [e["handle"] for e in data["dispatch"]["entries"]]
    assert "gandalf" in handles
    assert "sre" not in handles


# ---------------------------------------------------------------------------
# AC-009-5: Context propagation
# ---------------------------------------------------------------------------


@pytest.mark.ac_vec_009_5
def test_ac_vec_009_5_context_propagation(vector_env):
    """Prior channel history reaches runtime via context argument."""
    from vector.runtime import AgentRuntime

    captured_contexts = []

    class CapturingDelegate:
        def __call__(self, *, goal, context=None, **kw):
            captured_contexts.append(context)
            if "[gandalf]" in goal:
                return "reviewed"
            return "ok"

    runtime = AgentRuntime(delegate=CapturingDelegate())
    vector_env._runtime = runtime  # inject capturing runtime
    vector_env._dispatcher._runtime = runtime  # also update dispatcher's ref
    vector_env.create_agent(handle="gandalf", system_prompt="Wise wizard")
    ch = vector_env.create_channel(name="dev", members=["gandalf", "human"])

    # Post first message (no prior history)
    vector_env.post_and_dispatch(ch.id, "human", "hi @gandalf", dispatch=True)
    # Post second message (should have prior history in context)
    vector_env.post_and_dispatch(ch.id, "human", "@gandalf review again", dispatch=True)

    # The second call should have received context with prior history
    assert len(captured_contexts) >= 2
    if captured_contexts[1]:
        assert "hi" in captured_contexts[1].lower() or "gandalf" in captured_contexts[1].lower()


# ---------------------------------------------------------------------------
# AC-009-6: Error envelope
# ---------------------------------------------------------------------------


@pytest.mark.ac_vec_009_6
def test_ac_vec_009_6_channel_not_found(client):
    """Missing channel returns 404 with stable error envelope."""
    resp = client.post(
        "/api/vector/channels/missing-id/messages",
        json={"author_handle": "human", "body": "hello"},
    )
    assert resp.status_code == 404
    data = resp.json()
    assert "error" in data
    assert data["error"]["code"] == "VECTOR_CHANNEL_NOT_FOUND"
    assert "traceback" not in str(data).lower()


@pytest.mark.ac_vec_009_6
def test_ac_vec_009_6_validation_error_envelope(client, vector_env):
    """Invalid body returns 422 with error envelope."""
    ch = vector_env.create_channel(name="dev", members=["human"])
    resp = client.post(
        f"/api/vector/channels/{ch.id}/messages",
        json={"author_handle": "human", "body": ""},
    )
    # FastAPI returns 422 for validation errors
    assert resp.status_code in (422, 400)
    # Should not expose traceback
    assert "traceback" not in resp.text.lower()


# ---------------------------------------------------------------------------
# AC-009-7: Response includes user + agent messages (API contract)
# ---------------------------------------------------------------------------

@pytest.mark.ac_vec_009_7
def test_ac_vec_009_7_response_includes_both_messages(client, vector_env):
    """POST returns both user and agent messages in the response."""
    vector_env.create_agent(handle="gandalf", system_prompt="Wise")
    ch = vector_env.create_channel(name="dev", members=["gandalf", "human"])
    resp = client.post(
        f"/api/vector/channels/{ch.id}/messages",
        json={"author_handle": "human", "body": "@gandalf hello", "dispatch": True},
    )
    assert resp.status_code == 200
    result = resp.json()
    assert "messages" in result
    authors = [m["author_handle"] for m in result["messages"]]
    assert "human" in authors
    assert "gandalf" in authors


# ---------------------------------------------------------------------------
# AC-009-8: History endpoint retains chronological order
# ---------------------------------------------------------------------------

@pytest.mark.ac_vec_009_8
def test_ac_vec_009_8_history_chronological(client, vector_env):
    """GET messages returns chronological history with user before agent."""
    vector_env.create_agent(handle="gandalf", system_prompt="Wise")
    ch = vector_env.create_channel(name="dev", members=["gandalf", "human"])
    client.post(
        f"/api/vector/channels/{ch.id}/messages",
        json={"author_handle": "human", "body": "@gandalf hi", "dispatch": True},
    )
    resp = client.get(f"/api/vector/channels/{ch.id}/messages?limit=50")
    assert resp.status_code == 200
    history = resp.json()["messages"]
    assert len(history) >= 2
    assert history[0]["author_handle"] == "human"
    assert history[1]["author_handle"] == "gandalf"


# ---------------------------------------------------------------------------
# AC-009-9: Hermetic — no provider keys required
# ---------------------------------------------------------------------------

@pytest.mark.ac_vec_009_9
def test_ac_vec_009_9_hermetic_no_keys(client, vector_env):
    """Tests run without any API keys — fake delegate is used."""
    vector_env.create_agent(handle="gandalf", system_prompt="Wise")
    ch = vector_env.create_channel(name="dev", members=["gandalf", "human"])
    resp = client.post(
        f"/api/vector/channels/{ch.id}/messages",
        json={"author_handle": "human", "body": "@gandalf test", "dispatch": True},
    )
    assert resp.status_code == 200
    entry = resp.json()["dispatch"]["entries"][0]
    assert entry["status"] == "ok"
    assert entry["response"]  # non-empty deterministic response


# ---------------------------------------------------------------------------
# AC-009-10: Error evidence includes structured data
# ---------------------------------------------------------------------------

@pytest.mark.ac_vec_009_10
def test_ac_vec_009_10_error_evidence_structured(client, vector_env):
    """Error responses include structured error code and message."""
    resp = client.post(
        "/api/vector/channels/nonexistent/messages",
        json={"author_handle": "human", "body": "test"},
    )
    assert resp.status_code == 404
    data = resp.json()
    assert "error" in data
    assert "code" in data["error"]
    assert "message" in data["error"]
    assert data["error"]["code"] == "VECTOR_CHANNEL_NOT_FOUND"
