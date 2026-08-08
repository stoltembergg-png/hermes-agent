"""Contract tests for the Engineering Orchestrator pipeline."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "pipeline"))

from orchestrator import build_manifest, merge_gate, update_gates, update_role, write_manifest


def test_frontend_change_marks_backend_and_database_not_applicable():
    manifest = build_manifest(
        19,
        "message UI",
        "draft/pr-019",
        ["apps/desktop/src/plugins/vector-channels/plugin.tsx"],
    )
    statuses = {item["role"]: item["status"] for item in manifest["roles"]}
    assert statuses["frontend_engineer"] == "PENDING"
    assert statuses["backend_engineer"] == "NOT_APPLICABLE"
    assert statuses["database_engineer"] == "NOT_APPLICABLE"


def test_merge_gate_blocks_pending_roles_and_ci():
    manifest = build_manifest(41, "resilience", "feat/update-resilience-v2", ["scripts/install-vector.sh"])
    gate = merge_gate(manifest)
    assert gate["merge_allowed"] is False
    assert "role evidence incomplete or failed" in gate["reasons"]
    assert "required CI is not fully green" in gate["reasons"]


def test_manifest_can_be_promoted_only_with_evidence(tmp_path):
    manifest = build_manifest(41, "resilience", "feat/update-resilience-v2", ["scripts/install-vector.sh"])
    path = write_manifest(manifest, tmp_path)
    for role in (item["role"] for item in manifest["roles"]):
        if role in {"backend_engineer", "database_engineer"}:
            continue
        update_role(path, role, "PASS", [f"evidence/{role}.md"], "Verified by role contract test")
    update_gates(
        path,
        ci_green=True,
        tests_green=True,
        lint_green=True,
        security_green=True,
        worktree_clean=True,
        no_secrets=True,
    )
    promoted = json.loads(path.read_text(encoding="utf-8"))
    assert promoted["gates"]["merge_allowed"] is True


def test_invalid_role_status_is_rejected(tmp_path):
    manifest = build_manifest(1, "test", "branch", [])
    path = write_manifest(manifest, tmp_path)
    try:
        update_role(path, "product_manager", "APPROVED", ["x"], "bad status")
    except ValueError:
        pass
    else:
        raise AssertionError("invalid role status was accepted")


def test_quality_gate_blocks_regression_even_when_ci_is_green(tmp_path):
    manifest = build_manifest(2, "quality", "branch", [])
    path = write_manifest(manifest, tmp_path)
    for role in (item["role"] for item in manifest["roles"]):
        update_role(path, role, "PASS", [f"evidence/{role}.md"], "verified")
    stored = json.loads(path.read_text(encoding="utf-8"))
    stored["quality_gate"]["baseline_score"] = 101
    path.write_text(json.dumps(stored), encoding="utf-8")
    update_gates(
        path,
        ci_green=True,
        tests_green=True,
        lint_green=True,
        security_green=True,
        worktree_clean=True,
        no_secrets=True,
    )
    promoted = json.loads(path.read_text(encoding="utf-8"))
    assert promoted["gates"]["merge_allowed"] is False
    assert promoted["quality_gate"]["delta"] < 0


def test_protected_workflow_paths_block_promotion():
    manifest = build_manifest(
        3,
        "workflow change",
        "branch",
        [".github/workflows/ci.yml"],
        ci_green=True,
        worktree_clean=True,
        no_secrets=True,
    )
    assert manifest["quality_gate"]["protected_paths"] == [".github/workflows/ci.yml"]
    assert manifest["gates"]["merge_allowed"] is False
