"""Tests for pipeline runtime locking and durable state writes."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "pipeline"))

from runtime import PipelineAlreadyRunning, PipelineLock, atomic_write_json


def test_atomic_write_json_replaces_previous_content(tmp_path):
    path = tmp_path / "state.json"
    atomic_write_json(path, {"stage": "diagnose", "cycle": 1})
    atomic_write_json(path, {"stage": "orchestrate", "cycle": 1})
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "stage": "orchestrate",
        "cycle": 1,
    }
    assert not list(tmp_path.glob(".state.json.*"))


def test_pipeline_lock_rejects_second_owner(tmp_path):
    path = tmp_path / "run.lock"
    first = PipelineLock(path)
    second = PipelineLock(path)
    first.acquire()
    try:
        with pytest.raises(PipelineAlreadyRunning):
            second.acquire()
        details = json.loads(path.read_text(encoding="utf-8"))
        assert details["pid"] > 0
        assert details["started_at"]
    finally:
        first.release()
    second.acquire()
    second.release()


def test_pipeline_lock_releases_on_context_exit(tmp_path):
    path = tmp_path / "run.lock"
    with PipelineLock(path):
        assert path.exists()
    replacement = PipelineLock(path)
    replacement.acquire()
    replacement.release()
