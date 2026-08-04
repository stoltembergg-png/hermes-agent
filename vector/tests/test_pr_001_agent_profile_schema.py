"""Contract tests for PR-001 — Agent profile schema.

Each test corresponds to one AC listed in
docs/roadmap/prs/PR-001-agent-profile-schema.md and is tagged with the
matching ``@pytest.mark.ac_vec_001_N`` marker so the verify-feature.sh
script can collect ACs via ``pytest --collect-only`` and map them 1:1
to pass/fail results.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

# Allow running ``pytest`` from the repo root without installing the
# package; src/ is on sys.path for the test session.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from vector.profile import (
    AgentProfile,
    AgentRegistry,
    DuplicateHandleError,
    InvalidFallbackChainError,
    InvalidHandleError,
    UnknownModelError,
    validate_fallback_chain,
    validate_handle,
    validate_model_catalog,
)


def _sample_profile(**overrides) -> AgentProfile:
    """Return a valid AgentProfile, optionally overridden."""
    base = {
        "handle": "gandalf",
        "system_prompt": "You are a code reviewer.",
        "tools": ("read_file", "search_files"),
        "model": "anthropic/claude-sonnet-4.5",
        "provider": None,
        "fallback_models": ("openai/gpt-4o",),
        "description": "Reviewer",
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
        "updated_at": datetime(2026, 1, 1, tzinfo=UTC),
    }
    base.update(overrides)
    return AgentProfile(**base)


# ---------------------------------------------------------------------------
# @spec:AC-VEC-001-1 — YAML round-trip
# ---------------------------------------------------------------------------


@pytest.mark.ac_vec_001_1
def test_ac_vec_001_1_yaml_round_trip():
    """@spec:AC-VEC-001-1 — dump_yaml / load_yaml round-trip equals input."""
    p = _sample_profile()
    yaml_text = p.to_yaml()
    parsed = AgentProfile.from_yaml(yaml_text)
    assert parsed == p, "YAML round-trip must produce an equal profile"


# ---------------------------------------------------------------------------
# @spec:AC-VEC-001-2 — JSON round-trip
# ---------------------------------------------------------------------------


@pytest.mark.ac_vec_001_2
def test_ac_vec_001_2_json_round_trip():
    """@spec:AC-VEC-001-2 — dump_json / load_json round-trip equals input."""
    p = _sample_profile()
    json_text = p.to_json()
    parsed = AgentProfile.from_json(json_text)
    assert parsed == p, "JSON round-trip must produce an equal profile"


# ---------------------------------------------------------------------------
# @spec:AC-VEC-001-3 — invalid handle raises
# ---------------------------------------------------------------------------


@pytest.mark.ac_vec_001_3
@pytest.mark.parametrize(
    "bad_handle",
    [
        "Gandalf",          # uppercase — must be lowercase
        "with space",       # whitespace
        "x" * 33,           # too long (33 > 32)
        "",                 # empty
        "!nvalid",          # punctuation outside [a-z0-9._-]
        "han!dle",          # punctuation in the middle
        "çedilha",          # non-ASCII
    ],
)
def test_ac_vec_001_3_invalid_handle_raises(bad_handle):
    """@spec:AC-VEC-001-3 — invalid handle raises InvalidHandleError with offending value."""
    with pytest.raises(InvalidHandleError) as exc:
        AgentProfile(handle=bad_handle, system_prompt="x")
    assert repr(bad_handle) in str(exc.value), (
        f"error message must include the offending value {bad_handle!r}; got: {exc.value}"
    )


# ---------------------------------------------------------------------------
# @spec:AC-VEC-001-4 — duplicate registration raises
# ---------------------------------------------------------------------------


@pytest.mark.ac_vec_001_4
def test_ac_vec_001_4_duplicate_handle_raises():
    """@spec:AC-VEC-001-4 — AgentRegistry.register raises DuplicateHandleError on duplicate."""
    reg = AgentRegistry()
    reg.register(_sample_profile())
    with pytest.raises(DuplicateHandleError):
        reg.register(_sample_profile())


# ---------------------------------------------------------------------------
# @spec:AC-VEC-001-5 — unknown model raises
# ---------------------------------------------------------------------------


@pytest.mark.ac_vec_001_5
def test_ac_vec_001_5_unknown_model_raises():
    """@spec:AC-VEC-001-5 — constructing with unknown model raises UnknownModelError."""
    fake_catalog = lambda m: m == "anthropic/claude-sonnet-4.5"

    with pytest.raises(UnknownModelError):
        # The catalog validation is opt-in (None skips); we want the
        # explicit catalog_provider to reject this.
        validate_model_catalog(
            "gpt-9000/imaginary", None, catalog_provider=fake_catalog
        )


# ---------------------------------------------------------------------------
# @spec:AC-VEC-001-6 — fallback containing primary raises; empty is OK
# ---------------------------------------------------------------------------


@pytest.mark.ac_vec_001_6
def test_ac_vec_001_6_invalid_fallback_chain_raises():
    """@spec:AC-VEC-001-6 — fallback_models containing primary raises; empty is valid."""
    # Empty is valid (means "no fallback").
    assert validate_fallback_chain("anthropic/x", ()) == ()

    # Primary in fallback raises.
    with pytest.raises(InvalidFallbackChainError):
        validate_fallback_chain(
            "anthropic/claude-sonnet-4.5",
            ("anthropic/claude-sonnet-4.5", "openai/gpt-4o"),
        )

    # Duplicate fallbacks raise.
    with pytest.raises(InvalidFallbackChainError):
        validate_fallback_chain(
            "anthropic/claude-sonnet-4.5",
            ("openai/gpt-4o", "openai/gpt-4o"),
        )


# ---------------------------------------------------------------------------
# @spec:AC-VEC-001-7 — model=None / provider=None valid (inherit)
# ---------------------------------------------------------------------------


@pytest.mark.ac_vec_001_7
def test_ac_vec_001_7_none_model_and_provider_valid():
    """@spec:AC-VEC-001-7 — model=None and provider=None are valid (inherit)."""
    p = AgentProfile(handle="inheritor", system_prompt="inherit everything")
    assert p.model is None
    assert p.provider is None
    assert p.fallback_models == ()
    # Round-trips still work with None values.
    assert AgentProfile.from_json(p.to_json()) == p
    assert AgentProfile.from_yaml(p.to_yaml()) == p


# ---------------------------------------------------------------------------
# Extra invariants that the ACs imply but do not directly assert.
# These are NOT marked with @spec:AC markers and therefore must NOT
# be counted in the contract test pass/fail summary.
# ---------------------------------------------------------------------------


def test_registry_get_remove_and_listing():
    reg = AgentRegistry()
    a = _sample_profile(handle="alpha")
    b = _sample_profile(handle="bravo")
    reg.register(a)
    reg.register(b)
    assert sorted(reg.all(), key=lambda p: p.handle) == [a, b]
    assert reg.get("alpha") is a
    assert "alpha" in reg
    reg.remove("alpha")
    assert "alpha" not in reg


def test_validate_handle_helper_accepts_valid():
    assert validate_handle("gandalf") == "gandalf"
    assert validate_handle("a.b-c_d") == "a.b-c_d"
    assert validate_handle("ab") == "ab"  # 2-char minimum
    assert validate_handle("a" * 32) == "a" * 32  # 32-char maximum
