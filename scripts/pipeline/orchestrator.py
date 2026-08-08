#!/usr/bin/env python3
"""Engineering Orchestrator contracts for the Vector PR pipeline.

The orchestrator is deliberately deterministic: it creates an auditable role
manifest and computes merge eligibility, but it never merges or pushes code.
Agents may fill role verdicts; the release gate remains local and explicit.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROLE_ORDER = (
    "product_manager",
    "architect",
    "technical_planner",
    "frontend_engineer",
    "backend_engineer",
    "database_engineer",
    "qa_engineer",
    "security_engineer",
    "code_reviewer",
    "devops_release_engineer",
)

STATUS_VALUES = {"PENDING", "PASS", "FAIL", "NOT_APPLICABLE"}
ROLE_LABELS = {
    "product_manager": "Product Manager",
    "architect": "Architect",
    "technical_planner": "Technical Planner",
    "frontend_engineer": "Frontend Engineer",
    "backend_engineer": "Backend Engineer",
    "database_engineer": "Database Engineer",
    "qa_engineer": "QA Engineer",
    "security_engineer": "Security Engineer",
    "code_reviewer": "Code Reviewer",
    "devops_release_engineer": "DevOps/Release Engineer",
}


@dataclass
class RoleResult:
    role: str
    label: str
    status: str
    evidence: list[str]
    notes: str = ""

    def valid(self) -> bool:
        return self.status in STATUS_VALUES and bool(self.evidence) and bool(self.notes)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def applicable_roles(paths: list[str]) -> dict[str, bool]:
    """Return applicability without skipping the role: N/A is still recorded."""
    normalized = [p.lower() for p in paths]
    frontend = any(p.startswith(("apps/desktop/", "web/", "ui-tui/")) for p in normalized)
    backend = any(p.startswith(("vector/", "gateway/", "plugins/", "agent/", "tools/")) for p in normalized)
    database = any(any(token in p for token in ("migration", "schema", "database", "state.db", "storage")) for p in normalized)
    return {
        "product_manager": True,
        "architect": True,
        "technical_planner": True,
        "frontend_engineer": frontend,
        "backend_engineer": backend,
        "database_engineer": database,
        "qa_engineer": True,
        "security_engineer": True,
        "code_reviewer": True,
        "devops_release_engineer": True,
    }


def initial_roles(paths: list[str]) -> list[RoleResult]:
    applicable = applicable_roles(paths)
    roles: list[RoleResult] = []
    for role in ROLE_ORDER:
        if applicable[role]:
            roles.append(RoleResult(role, ROLE_LABELS[role], "PENDING", [], "Awaiting role evidence"))
        else:
            roles.append(RoleResult(role, ROLE_LABELS[role], "NOT_APPLICABLE", ["Path classification"], "No files require this specialty"))
    return roles


def _all_checks_green(checks: list[dict[str, Any]]) -> bool:
    if not checks:
        return False
    allowed = {"SUCCESS", "SKIPPED"}
    return all(str(c.get("state", c.get("conclusion", ""))).upper() in allowed for c in checks)


def merge_gate(manifest: dict[str, Any]) -> dict[str, Any]:
    roles = manifest.get("roles", [])
    role_ok = all(r.get("status") in {"PASS", "NOT_APPLICABLE"} and r.get("evidence") and r.get("notes") for r in roles)
    ci_ok = bool(manifest.get("gates", {}).get("ci_green"))
    clean_ok = bool(manifest.get("gates", {}).get("worktree_clean"))
    secrets_ok = bool(manifest.get("gates", {}).get("no_secrets"))
    reasons = []
    if not role_ok:
        reasons.append("role evidence incomplete or failed")
    if not ci_ok:
        reasons.append("required CI is not fully green")
    if not clean_ok:
        reasons.append("worktree is not clean")
    if not secrets_ok:
        reasons.append("secret scan did not pass")
    return {"merge_allowed": not reasons, "reasons": reasons}


def build_manifest(
    pr: int,
    title: str,
    head_ref: str,
    paths: list[str],
    *,
    identity: dict[str, str] | None = None,
    ci_green: bool = False,
    worktree_clean: bool = False,
    no_secrets: bool = False,
) -> dict[str, Any]:
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "pr": pr,
        "title": title,
        "head_ref": head_ref,
        "created_at": utc_now(),
        "orchestrator": "engineering-orchestrator",
        "identity": identity or {},
        "role_order": list(ROLE_ORDER),
        "roles": [asdict(r) for r in initial_roles(paths)],
        "evidence": {"changed_files": paths},
        "gates": {
            "ci_green": ci_green,
            "worktree_clean": worktree_clean,
            "no_secrets": no_secrets,
        },
    }
    manifest["gates"].update(merge_gate(manifest))
    return manifest


def write_manifest(manifest: dict[str, Any], root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"pr-{manifest['pr']}.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def update_role(manifest_path: Path, role: str, status: str, evidence: list[str], notes: str) -> dict[str, Any]:
    if status not in STATUS_VALUES:
        raise ValueError(f"invalid role status: {status}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for item in manifest["roles"]:
        if item["role"] == role:
            item.update({"status": status, "evidence": evidence, "notes": notes})
            break
    else:
        raise KeyError(role)
    manifest["gates"].update(merge_gate(manifest))
    write_manifest(manifest, manifest_path.parent)
    return manifest


def update_gates(manifest_path: Path, **gates: bool) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["gates"].update({key: bool(value) for key, value in gates.items()})
    manifest["gates"].update(merge_gate(manifest))
    write_manifest(manifest, manifest_path.parent)
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pr", type=int, required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--head-ref", required=True)
    parser.add_argument("--files", nargs="*", default=[])
    parser.add_argument("--manifest-dir", type=Path, default=Path(".pipeline/manifests"))
    parser.add_argument("--ci-green", action="store_true")
    parser.add_argument("--worktree-clean", action="store_true")
    parser.add_argument("--no-secrets", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = build_manifest(
        args.pr,
        args.title,
        args.head_ref,
        args.files,
        ci_green=args.ci_green,
        worktree_clean=args.worktree_clean,
        no_secrets=args.no_secrets,
    )
    path = write_manifest(manifest, args.manifest_dir)
    print(json.dumps({"manifest": str(path), "gates": manifest["gates"], "roles": manifest["roles"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
