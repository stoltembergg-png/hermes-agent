#!/usr/bin/env python3
"""Create a reproducible quality baseline for the current clean main checkout."""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

WEIGHTS = {
    "tests_green": 25,
    "lint_green": 20,
    "security_green": 20,
    "ci_green": 20,
    "worktree_clean": 5,
    "no_secrets": 10,
}
REPO = "stoltembergg-png/hermes-agent"
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
SECRET_RE = re.compile(
    r"(?:BEGIN (?:RSA|OPENSSH|EC) PRIVATE KEY|"
    r"ghp_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{20,}|"
    r"password\s*[:=]\s*['\"][A-Za-z0-9+/=_-]{12,}['\"])",
    re.IGNORECASE,
)


def run(command: list[str], cwd: Path, timeout: int = 180) -> dict[str, Any]:
    result = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        env={**os.environ, "GH_FORCE_TTY": "0", "GH_PAGER": "cat"},
    )
    return {
        "command": command,
        "returncode": result.returncode,
        "stdout_tail": ANSI_RE.sub("", result.stdout)[-4000:],
        "stderr_tail": ANSI_RE.sub("", result.stderr)[-2000:],
    }


def score(dimensions: dict[str, bool]) -> int:
    return sum(weight for key, weight in WEIGHTS.items() if dimensions.get(key) is True)


def scan_secrets(root: Path) -> tuple[bool, list[str]]:
    files = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        capture_output=True,
        check=False,
    )
    findings: list[str] = []
    for raw_path in files.stdout.split(b"\0"):
        if not raw_path:
            continue
        path = Path(os.fsdecode(raw_path))
        if (
            any(part in {"tests", "test", "fixtures", "docs", "skills"} for part in path.parts)
            or path.name.endswith(".example")
            or path.name.endswith(".example.yaml")
            or path.name.endswith(".example.yml")
            or path.name == "redact.py"
        ):
            continue
        try:
            content = (root / path).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for line_number, line in enumerate(content.splitlines(), 1):
            if SECRET_RE.search(line):
                findings.append(f"{path}:{line_number}")
    return not findings, findings


def create_baseline(root: Path) -> dict[str, Any]:
    status = run(["git", "status", "--porcelain"], root)
    branch = run(["git", "branch", "--show-current"], root)
    sha = run(["git", "rev-parse", "HEAD"], root)
    if status["returncode"] != 0 or status["stdout_tail"].strip():
        raise RuntimeError("baseline requires a clean worktree")
    if sha["returncode"] != 0:
        raise RuntimeError("could not resolve baseline SHA")

    test_run = run(
        [
            "/home/ec2-user/hermes-vector-venv/bin/python",
            "-m",
            "pytest",
            "vector/tests/",
            "-q",
            "--tb=line",
        ],
        root,
        timeout=300,
    )
    lint_run = run(
        ["/home/ec2-user/hermes-vector-venv/bin/ruff", "check", "scripts/pipeline", "vector/tests"],
        root,
        timeout=120,
    )
    secrets_ok, secret_findings = scan_secrets(root)
    ci_run = run(
        [
            "gh",
            "run",
            "list",
            "--repo",
            REPO,
            "--branch",
            "main",
            "--commit",
            sha["stdout_tail"].strip(),
            "--json",
            "status,conclusion,name,headSha",
            "--limit",
            "100",
        ],
        root,
        timeout=60,
    )
    try:
        ci_runs = json.loads(ci_run["stdout_tail"]) if ci_run["returncode"] == 0 else []
    except json.JSONDecodeError:
        ci_runs = []
    ci_green = bool(ci_runs) and all(
        item.get("status") == "completed" and item.get("conclusion") in {"success", "skipped"}
        for item in ci_runs
    )
    dimensions = {
        "tests_green": test_run["returncode"] == 0,
        "lint_green": lint_run["returncode"] == 0,
        "security_green": secrets_ok,
        "ci_green": ci_green,
        "worktree_clean": True,
        "no_secrets": secrets_ok,
    }
    baseline_sha = sha["stdout_tail"].strip()
    return {
        "schema_version": 1,
        "baseline_id": f"main:{baseline_sha}",
        "repo": REPO,
        "branch": branch["stdout_tail"].strip(),
        "sha": baseline_sha,
        "score": score(dimensions),
        "weights": WEIGHTS,
        "dimensions": dimensions,
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
        },
        "evidence": {
            "status": status,
            "tests": test_run,
            "lint": lint_run,
            "security": {"command": ["tracked-file-secret-scan"], "findings": secret_findings},
            "ci": {**ci_run, "runs": ci_runs},
        },
    }


def atomic_write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with open(fd, "w", encoding="utf-8", closefd=True) as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("/home/ec2-user/.hermes/pipeline/baselines/main-current.json"),
    )
    args = parser.parse_args()
    baseline = create_baseline(args.root.resolve())
    atomic_write(args.output, baseline)
    print(json.dumps({"baseline": str(args.output), "id": baseline["baseline_id"], "score": baseline["score"], "dimensions": baseline["dimensions"]}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
