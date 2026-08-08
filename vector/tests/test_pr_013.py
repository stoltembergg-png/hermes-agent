"""Contract tests for PR-013 — Provider/model picker in the Add Agent modal.

Validates the backend half of the roadmap ACs:

- The vector-channels dashboard plugin exposes a ``GET /models`` route.
- The route returns the Hermes provider/model catalog (providers + their
  curated model lists), reusing the same shared builder as the dashboard
  ``/api/model/options`` endpoint and the TUI ``model.options`` JSON-RPC
  method (``hermes_cli.inventory.build_model_options_payload``).
- The route does NOT touch the VectorService — the model catalog is a
  Hermes-core concern, not a vector concern. (We assert this by deleting
  the service init and confirming ``/models`` still works.)
- Each provider row is trimmed to the ``{slug, name, models}`` shape the
  desktop picker renders (no pricing/capabilities blobs leak through).
- The top-level ``model``/``provider`` carry the session's current
  selection so a future UX can mark the current row.
- A builder failure degrades to a structured ``VECTOR_MODEL_OPTIONS_FAILED``
  error envelope instead of a 500 traceback.

The frontend half (the ``<details>`` Advanced section + provider/model
``<select>`` dropdowns in ``AddAgentModal``) is a UI-convention smoke
check here — validating the real React rendering is left to a Playwright
harness in v1, matching PR-007's split.
"""

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
def plugin_client(monkeypatch):
    """FastAPI TestClient with the vector-channels plugin router mounted.

    The ``GET /models`` handler is a pure proxy into the Hermes model
    resolver — it does not call VectorService — so we mount the plugin
    router on a bare FastAPI app and assert the service layer is never
    touched. ``build_model_options_payload`` is monkeypatched so the test
    does not depend on any real provider credentials.
    """
    # Stub the Hermes model resolver BEFORE importing plugin_api, so the
    # the module-level import-only-once guards don't drag in vector.
    # (plugin_api still imports vector.service lazily behind try/except; we
    # don't need it for /models.)
    import hermes_cli.inventory as inventory

    _fake_payload = {
        "providers": [
            {"slug": "nous", "name": "Nous", "models": ["nous-hermes-1"],
             "total_models": 1, "is_current": True,
             "authenticated": True, "extra_pruning_field": "DROP_ME"},
            {"slug": "openrouter", "name": "OpenRouter",
             "models": ["anthropic/claude-sonnet-5", "google/gemini-2.5-pro"],
             "total_models": 2, "is_current": False,
             "authenticated": True, "extra_pricing": {"x": 1}},
        ],
        "model": "nous-hermes-1",
        "provider": "nous",
    }

    def _fake_build(ctx, **kwargs):
        return _fake_payload

    monkeypatch.setattr(inventory, "build_model_options_payload", _fake_build)
    # load_picker_context is called too — return a sentinel (it's passed
    # through to build_model_options_payload which ignores it under our
    # fake).
    monkeypatch.setattr(inventory, "load_picker_context", lambda: "ctx")

    import plugin_api

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(plugin_api.router, prefix="/api/plugins/vector-channels")
    return TestClient(app)


# ---------------------------------------------------------------------------
# AC-VEC-013-1: GET /models route exists and returns the provider catalog
# ---------------------------------------------------------------------------


@pytest.mark.ac_vec_013_1
def test_pr_013_models_endpoint_returns_providers(plugin_client):
    """GET /models returns 200 with a ``providers`` array.

    Each provider row carries ``slug`` + ``models`` so the Add Agent
    modal can populate its provider/model dropdowns.
    """
    resp = plugin_client.get("/api/plugins/vector-channels/models")
    assert resp.status_code == 200
    data = resp.json()

    assert "providers" in data
    assert isinstance(data["providers"], list)
    assert len(data["providers"]) == 2

    nous = next(p for p in data["providers"] if p["slug"] == "nous")
    assert nous["name"] == "Nous"
    assert "nous-hermes-1" in nous["models"]
    assert isinstance(nous["models"], list)


# ---------------------------------------------------------------------------
# AC-VEC-013-2: provider rows are trimmed to {slug, name, models}
# ---------------------------------------------------------------------------


@pytest.mark.ac_vec_013_2
def test_pr_013_provider_rows_trimmed_to_picker_shape(plugin_client):
    """Only the fields the desktop picker renders are shipped.

    The underlying ``build_model_options_payload`` row carries pricing,
    capabilities, ``authenticated`` hints, etc. — none of which the Add
    Agent modal renders. The /models endpoint must trim each row to
    ``{slug, name, models}`` so we don't ship blobs the UI ignores.
    """
    resp = plugin_client.get("/api/plugins/vector-channels/models")
    rows = resp.json()["providers"]

    for row in rows:
        assert set(row.keys()) == {"slug", "name", "models"}, (
            f"row {row.get('slug')!r} must be trimmed to {{slug, name, models}}, "
            f"got {sorted(row.keys())}"
        )
        assert isinstance(row["models"], list)


# ---------------------------------------------------------------------------
# AC-VEC-013-3: top-level model/provider carry the session's current selection
# ---------------------------------------------------------------------------


@pytest.mark.ac_vec_013_3
def test_pr_013_current_selection_surfaced(plugin_client):
    """``model``/``provider`` (top level) mirror the session selection.

    Mirrors ``/api/model/options``: the payload carries the current
    model/provider so a future UX can mark the current row. The Add Agent
    modal does not render this marker yet, but the contract must hold.
    """
    resp = plugin_client.get("/api/plugins/vector-channels/models")
    data = resp.json()

    assert data["model"] == "nous-hermes-1"
    assert data["provider"] == "nous"


# ---------------------------------------------------------------------------
# AC-VEC-013-4: /models does NOT touch the VectorService
# ---------------------------------------------------------------------------


@pytest.mark.ac_vec_013_4
def test_pr_013_models_does_not_touch_vector_service(plugin_client, monkeypatch):
    """The model catalog is a Hermes-core concern, not a vector one.

    ``/models`` must work even if the VectorService was never initialised.
    We assert this by ensuring ``_get_service`` is never invoked while
    serving ``/models``. (The stub would also fail loudly if it were,
    because we point it at a non-callable here.) This is the load-bearing
    reason the handler imports ``build_model_options_payload`` directly
    rather than delegating through the service.
    """
    import plugin_api

    def _boom():
        raise AssertionError(
            "GET /models must not call _get_service() — the model catalog "
            "is a Hermes-core concern, not VectorService."
        )

    monkeypatch.setattr(plugin_api, "_get_service", _boom)

    resp = plugin_client.get("/api/plugins/vector-channels/models")
    assert resp.status_code == 200
    assert "providers" in resp.json()


# ---------------------------------------------------------------------------
# AC-VEC-013-5: builder failure degrades to the structured error envelope
# ---------------------------------------------------------------------------


@pytest.mark.ac_vec_013_5
def test_pr_013_models_builder_failure_returns_error_envelope(monkeypatch):
    """If ``build_model_options_payload`` raises, we return the shaped
    ``VECTOR_MODEL_OPTIONS_FAILED`` envelope — never a 500 traceback.

    A failed model-list fetch is non-fatal for the modal: the user can
    still create an agent with session-inherited defaults. The endpoint
    must surface the failure as a parseable error envelope matching the
    rest of the vector API (``{error: {code, message, retryable}}``).
    """
    import hermes_cli.inventory as inventory

    def _broken(ctx, **kwargs):
        raise RuntimeError("model catalog exploded")

    monkeypatch.setattr(inventory, "build_model_options_payload", _broken)
    monkeypatch.setattr(inventory, "load_picker_context", lambda: "ctx")

    import plugin_api
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(plugin_api.router, prefix="/api/plugins/vector-channels")
    client = TestClient(app)

    resp = client.get("/api/plugins/vector-channels/models")
    assert resp.status_code == 500
    body = resp.json()
    assert body["error"]["code"] == "VECTOR_MODEL_OPTIONS_FAILED"
    assert "model catalog exploded" in body["error"]["message"]
    assert body["error"]["retryable"] is False


# ---------------------------------------------------------------------------
# AC-VEC-013-6: frontend half smoke-check (AddAgentModal Advanced section)
# ---------------------------------------------------------------------------


@pytest.mark.ac_vec_013_6
def test_pr_013_add_agent_modal_has_advanced_picker():
    """The Add Agent modal ships the provider/model picker (PR-013 UI).

    v0 smoke check (mirrors PR-007's split): assert the plugin source
    contains the Advanced ``<details>`` section + provider/model
    ``<select>`` dropdowns, fetches the catalog on mount, and omits
    empty model/provider from the createAgent request. A Playwright
    harness exercises the live React rendering in v1.
    """
    plugin_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "apps", "desktop", "src",
        "plugins", "vector-channels", "plugin.tsx",
    )
    assert os.path.exists(plugin_path), f"plugin.tsx missing at {plugin_path}"
    with open(plugin_path, encoding="utf-8") as f:
        content = f.read()

    # Provider/model catalog client lives in api.ts.
    api_path = os.path.join(os.path.dirname(plugin_path), "api.ts")
    with open(api_path, encoding="utf-8") as f:
        api_content = f.read()

    # Frontend wiring.
    assert "getModelOptions" in api_content, "api.ts must export getModelOptions()"
    assert "ModelOptionProvider" in api_content, "api.ts must export ModelOptionProvider type"
    assert "ModelOptionsResponse" in api_content, "api.ts must export ModelOptionsResponse type"

    # Modal mounts a <details> Advanced section (PR-013 spec #1).
    assert "<summary>Advanced</summary>" in content, (
        "AddAgentModal must render a <details><summary>Advanced</summary> "
        "collapsible section"
    )

    # Provider + model <select> dropdowns with empty defaults =
    # "Inherit from session" / "Inherit" (spec #2, #3).
    assert "vector-add-agent-provider" in content, "provider <select> missing"
    assert "vector-add-agent-model" in content, "model <select> missing"
    assert 'value="">Inherit from session</option>' in content, (
        "provider dropdown must default to an empty 'Inherit from session' option"
    )
    # The model dropdown defaults to a distinct "Inherit" empty option (the
    # provider dropdown uses "Inherit from session"). Match the exact option
    # tag rather than a bare substring so we don't false-match the provider label.
    assert '<option value="">Inherit</option>' in content, (
        "model dropdown must default to an empty 'Inherit' option"
    )

    # Catalog is fetched on modal mount (spec: useEffect fetch).
    assert "useEffect" in content, "plugin must use useEffect to fetch the catalog"
    assert "getModelOptions()" in content, "modal must call getModelOptions() on mount"

    # Empty model/provider are omitted from the request (spec #5):
    # the createAgent call builds the request object and only adds
    # provider/model when truthy, instead of always including them.
    assert "req.provider = provider" in content, (
        "modal must conditionally set req.provider (omit when empty)"
    )
    assert "req.model = model" in content, (
        "modal must conditionally set req.model (omit when empty)"
    )

    # Model dropdown is filtered by selected provider (spec #3):
    # modelOptions derives from the picked provider's models list.
    assert "providers.find" in content, (
        "model options must be filtered by the selected provider's row"
    )
