"""Contract tests for PR-002 — @mention parser.

Each test corresponds to one AC listed in
docs/roadmap/prs/PR-002-mention-parser.md and is tagged with the
matching ``@pytest.mark.ac_vec_002_N`` marker so the
verify-feature.sh script can collect ACs via ``pytest --collect-only``
and map them 1:1 to pass/fail results.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from vector.mention import MENTION_CAP, extract_mentions

# ---------------------------------------------------------------------------
# @spec:AC-VEC-002-1 — basic mention extraction
# ---------------------------------------------------------------------------


@pytest.mark.ac_vec_002_1
def test_ac_vec_002_1_basic_mention():
    """@spec:AC-VEC-002-1 — "hi @gandalf" → ["gandalf"]."""
    assert extract_mentions("hi @gandalf") == ["gandalf"]


# ---------------------------------------------------------------------------
# @spec:AC-VEC-002-2 — email-like patterns must NOT match
# ---------------------------------------------------------------------------


@pytest.mark.ac_vec_002_2
def test_ac_vec_002_2_email_not_matched():
    """@spec:AC-VEC-002-2 — "contact user@example.com" → []."""
    assert extract_mentions("contact user@example.com") == []


# ---------------------------------------------------------------------------
# @spec:AC-VEC-002-3 — known multi-word names
# ---------------------------------------------------------------------------


@pytest.mark.ac_vec_002_3
def test_ac_vec_002_3_known_multiname():
    """@spec:AC-VEC-002-3 — known multi-word name matched whole."""
    assert extract_mentions(
        "@code-review-bot please look",
        known_names=["code-review-bot"],
    ) == ["code-review-bot"]


# ---------------------------------------------------------------------------
# @spec:AC-VEC-002-4 — fenced + inline code excluded
# ---------------------------------------------------------------------------


@pytest.mark.ac_vec_002_4
def test_ac_vec_002_4_code_exclusion():
    """@spec:AC-VEC-002-4 — fenced and inline code excluded."""
    # ``@gandalf`` inside triple backticks is invisible; ``@frodo``
    # inside single backticks is also invisible. Result: empty.
    text = "see ```@gandalf``` and `@frodo`"
    assert extract_mentions(text) == []


# ---------------------------------------------------------------------------
# @spec:AC-VEC-002-5 — dedup + order preserved
# ---------------------------------------------------------------------------


@pytest.mark.ac_vec_002_5
def test_ac_vec_002_5_dedup_order():
    """@spec:AC-VEC-002-5 — "@a @b @a" → ["a", "b"] (no duplicates, order preserved)."""
    assert extract_mentions("@a @b @a") == ["a", "b"]


# ---------------------------------------------------------------------------
# @spec:AC-VEC-002-6 — determinism
# ---------------------------------------------------------------------------


@pytest.mark.ac_vec_002_6
def test_ac_vec_002_6_deterministic():
    """@spec:AC-VEC-002-6 — calling twice with same input returns equal lists."""
    text = "@gandalf @frodo @gandalf @smeagol"
    first = extract_mentions(text)
    second = extract_mentions(text)
    assert first == second
    # First call is also deterministic in shape: dedup + lowercase.
    assert first == ["gandalf", "frodo", "smeagol"]


# ---------------------------------------------------------------------------
# Extra invariants the ACs imply but do not directly assert.
# ---------------------------------------------------------------------------


def test_empty_string_returns_empty_list():
    assert extract_mentions("") == []
    assert extract_mentions("no at signs here") == []


def test_only_at_sign_returns_empty_list():
    assert extract_mentions("@") == []


def test_known_name_longest_first():
    """Longest match wins when two known names share a prefix."""
    names = ["reviewer", "reviewer-bot"]
    # Input "@reviewer-bot" could match either; longest-first means
    # we get the bot.
    assert extract_mentions("@reviewer-bot", known_names=names) == ["reviewer-bot"]
    # But bare "@reviewer" still matches "reviewer".
    assert extract_mentions("@reviewer", known_names=names) == ["reviewer"]


def test_mention_cap_truncates():
    """Beyond MENTION_CAP distinct mentions the result is truncated."""
    handles = " ".join(f"@h{i}" for i in range(MENTION_CAP + 5))
    result = extract_mentions(handles)
    assert len(result) == MENTION_CAP
    # First-seen order preserved.
    assert result[0] == "h0"
    assert result[-1] == f"h{MENTION_CAP - 1}"
