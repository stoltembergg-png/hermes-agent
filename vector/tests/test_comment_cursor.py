"""Contract tests for incremental PR comment collection."""
from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path.home() / ".hermes/scripts/collect-vector-pr-comments.py"
SPEC = importlib.util.spec_from_file_location("vector_comment_collector", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_incremental_entries_returns_new_and_updated_only():
    entries = [
        {"id": 1, "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z"},
        {"id": 2, "created_at": "2026-01-02T00:00:00Z", "updated_at": "2026-01-03T00:00:00Z"},
        {"id": 3, "created_at": "2026-01-04T00:00:00Z", "updated_at": "2026-01-04T00:00:00Z"},
    ]
    fresh, cursor = MODULE.incremental_entries(
        entries,
        {"1": "2026-01-01T00:00:00Z", "2": "2026-01-02T00:00:00Z"},
    )
    assert [item["id"] for item in fresh] == [2, 3]
    assert cursor == {
        "1": "2026-01-01T00:00:00Z",
        "2": "2026-01-03T00:00:00Z",
        "3": "2026-01-04T00:00:00Z",
    }


def test_head_sha_change_resets_previous_cursor():
    old = {"head_sha": "old", "comments": {"1": "same"}}
    current_sha = "new"
    previous = old["comments"] if old["head_sha"] == current_sha else {}
    fresh, _ = MODULE.incremental_entries(
        [{"id": 1, "created_at": "same", "updated_at": "same"}], previous
    )
    assert [item["id"] for item in fresh] == [1]
