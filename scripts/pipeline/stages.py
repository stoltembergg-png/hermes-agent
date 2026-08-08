#!/usr/bin/env python3
"""
Vector Development Pipeline — State Machine
Determines which stage to execute based on repo state.

Stages:
  1. Diagnose    — assess PRs, CI status, backlog
  2. Implement   — implement next PR from roadmap
  3. Lint+Test   — run eslint --fix + pytest on all open PR branches
  4. Merge       — merge all PRs with green CI
  5. Fix CI      — fix failing CI on open PRs
  6. Learn       — Better Harness analysis + skill updates

State is persisted in /home/ec2-user/.hermes/pipeline/state.json
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from orchestrator import build_manifest, merge_gate, update_gates, update_role, write_manifest

REPO = os.environ.get("VECTOR_REPO", str(Path(__file__).resolve().parents[2]))
STATE_FILE = Path(os.environ.get("VECTOR_PIPELINE_STATE", "/home/ec2-user/.hermes/pipeline/state.json"))
MANIFEST_DIR = Path(os.environ.get("VECTOR_PIPELINE_MANIFESTS", "/home/ec2-user/.hermes/pipeline/manifests"))
STAGES = [
    "diagnose",
    "orchestrate",
    "implement",
    "lint_test",
    "security_review",
    "code_review",
    "release",
    "merge",
    "fix_ci",
    "learn",
]


def load_state():
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"last_stage": None, "last_run": None, "cycle": 0, "history": []}


def save_state(state):
    state["history"].append({
        "stage": state["last_stage"],
        "timestamp": state["last_run"],
        "cycle": state["cycle"],
    })
    if len(state["history"]) > 50:
        state["history"] = state["history"][-50:]
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def next_stage(state):
    if state["last_stage"] is None:
        return 0  # Start with diagnose
    idx = STAGES.index(state["last_stage"])
    return (idx + 1) % len(STAGES)


def run_cmd(cmd, timeout=30):
    env = os.environ.copy()
    env["GH_FORCE_TTY"] = "0"
    env["GH_PAGER"] = "cat"
    # Ensure gh has auth token
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        # Try to read from config
        gh_hosts = Path.home() / ".config" / "gh" / "hosts.yml"
        if gh_hosts.exists():
            for line in gh_hosts.read_text(encoding="utf-8").splitlines():
                if "oauth_token:" in line:
                    token = line.split("oauth_token:", 1)[1].strip()
                    break
    if token:
        env["GITHUB_TOKEN"] = token
    env["PATH"] = f"/home/ec2-user/.local/bin:/usr/local/bin:/usr/bin:/bin:{env.get('PATH', '')}"
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, encoding="utf-8", errors="replace",
                         timeout=timeout, cwd=REPO, env=env)
        # Strip ANSI escape codes from stdout
        import re
        stdout = re.sub(r'\x1b\[[0-9;]*m', '', r.stdout).strip()
        stderr = re.sub(r'\x1b\[[0-9;]*m', '', r.stderr).strip()
        return stdout, stderr, r.returncode
    except subprocess.TimeoutExpired:
        return "", "TIMEOUT", 124


# ============================================================
# STAGE 1: DIAGNOSE
# ============================================================
def stage_diagnose():
    """Assess all open PRs, CI status, and backlog."""
    print("=== STAGE 1: DIAGNOSE ===")
    results = {"open_prs": [], "ci_status": {}, "backlog": []}

    # Get open PRs
    out, _, _ = run_cmd(
        "gh pr list --repo stoltembergg-png/hermes-agent --state open --json number,title,headRefName,isDraft --limit 30"
    )
    try:
        prs = json.loads(out)
        results["open_prs"] = prs
        print(f"  Open PRs: {len(prs)}")
        for pr in prs:
            draft = " (DRAFT)" if pr.get("isDraft") else ""
            print(f"    #{pr['number']}: {pr['title']}{draft}")
    except json.JSONDecodeError:
        print("  Could not parse PR list")

    # Check CI for each PR
    for pr in results["open_prs"]:
        pr_num = pr["number"]
        out, _, _ = run_cmd(
            f"gh pr checks {pr_num} --repo stoltembergg-png/hermes-agent 2>&1 | head -3"
        )
        if "All checks were successful" in out:
            results["ci_status"][str(pr_num)] = "green"
            print(f"  PR #{pr_num}: CI GREEN")
        elif "failing" in out:
            results["ci_status"][str(pr_num)] = "failing"
            print(f"  PR #{pr_num}: CI FAILING")
        elif "pending" in out:
            results["ci_status"][str(pr_num)] = "pending"
            print(f"  PR #{pr_num}: CI PENDING")
        else:
            results["ci_status"][str(pr_num)] = "unknown"
            print(f"    PR #{pr_num}: CI UNKNOWN")

    # Backlog: PRs not yet created (PR-017 through PR-024)
    results["backlog"] = [
        "PR-017: Delete frontend (trash buttons) — 95% local",
        "PR-018: Channel member list + add/remove",
        "PR-020: Streaming responses",
        "PR-021: Message search",
        "PR-022: Notifications",
        "PR-023: Theming",
        "PR-024: Export",
    ]
    print(f"  Backlog: {len(results['backlog'])} PRs not started")

    return results


# ============================================================
# STAGE 2: ENGINEERING ORCHESTRATOR
# ============================================================
def stage_orchestrate():
    """Create/update auditable role manifests without changing branches."""
    print("=== STAGE 2: ENGINEERING ORCHESTRATOR ===")
    out, _, rc = run_cmd(
        "gh pr list --repo stoltembergg-png/hermes-agent --state open "
        "--json number,title,headRefName,headRefOid,baseRefOid --limit 30"
    )
    if rc != 0:
        return {"error": "could not read open PRs"}
    try:
        prs = json.loads(out)
    except json.JSONDecodeError:
        return {"error": "invalid PR list"}

    clean = not bool(run_cmd("git status --porcelain")[0].strip())
    results = []
    for pr in prs:
        number = pr["number"]
        files_out, _, files_rc = run_cmd(
            f"gh pr diff {number} --repo stoltembergg-png/hermes-agent --name-only"
        )
        paths = files_out.splitlines() if files_rc == 0 else []
        manifest = build_manifest(
            number,
            pr["title"],
            pr["headRefName"],
            paths,
            identity={
                "repo_root": REPO,
                "worktree": str(Path.cwd()),
                "branch": run_cmd("git branch --show-current")[0].strip(),
                "worktree_head_sha": run_cmd("git rev-parse HEAD")[0].strip(),
                "pr_head_sha": pr.get("headRefOid", ""),
                "base_sha": pr.get("baseRefOid", ""),
                "tracked_and_untracked_status": run_cmd("git status --porcelain")[0],
            },
            worktree_clean=clean,
            no_secrets=False,
        )
        path = write_manifest(manifest, MANIFEST_DIR)
        results.append({
            "pr": number,
            "manifest": str(path),
            "roles": {r["role"]: r["status"] for r in manifest["roles"]},
            "merge_allowed": manifest["gates"]["merge_allowed"],
        })
        print(f"  PR #{number}: manifest={path} merge_allowed=False (CI/role gates pending)")
    return {"manifests": results, "worktree_clean": clean}


# ============================================================
# STAGE 3: IMPLEMENT
# ============================================================
def stage_implement():
    """Implement next PR from roadmap."""
    print("=== STAGE 2: IMPLEMENT ===")
    print("  Checking backlog for next PR to implement...")
    print("  Next: PR-017 (Delete frontend — 95% local)")
    print("  Next: PR-018 (Channel member list)")
    print("  (Agent decides based on diagnose results)")
    return {"action": "delegate", "target": "PR-017"}


# ============================================================
# STAGE 3: LINT + TEST
# ============================================================
def stage_lint_test():
    """Validate only the current worktree; never switch another PR's branch."""
    print("=== STAGE 3: LINT + TEST ===")
    branch = run_cmd("git branch --show-current")[0].strip()
    before = run_cmd("git status --porcelain")[0].strip()
    _, eslint_err, eslint_rc = run_cmd(
        "npx eslint apps/desktop/src/plugins/vector-channels/plugin.tsx "
        "apps/desktop/src/plugins/vector-channels/api.ts --fix",
        timeout=60,
    )
    out, err, pytest_rc = run_cmd(
        "source venv/bin/activate && python3 -m pytest vector/tests/ -q --tb=line 2>&1 | tail -5",
        timeout=60,
    )
    print(f"  Contract tests: {out}")
    after = run_cmd("git status --porcelain")[0].strip()
    return {
        "branch": branch,
        "eslint_exit": eslint_rc,
        "pytest_exit": pytest_rc,
        "dirty_before": bool(before),
        "dirty_after": bool(after),
        "changes_require_review": bool(after),
        "stderr": (eslint_err or err)[-500:],
    }


# ============================================================
# STAGES 5-7: ROLE GATES
# ============================================================
def _current_pr_manifest() -> Path | None:
    out, _, rc = run_cmd("gh pr view --repo stoltembergg-png/hermes-agent --json number")
    if rc != 0:
        return None
    try:
        number = json.loads(out)["number"]
    except (json.JSONDecodeError, KeyError):
        return None
    path = MANIFEST_DIR / f"pr-{number}.json"
    return path if path.exists() else None


def stage_security_review():
    """Run a secret-pattern scan and record Security Engineer evidence."""
    print("=== STAGE 5: SECURITY REVIEW ===")
    manifest = _current_pr_manifest()
    if manifest is None:
        return {"status": "PENDING", "reason": "no current PR manifest"}
    diff = run_cmd("git diff --binary HEAD^..HEAD")[0]
    secret_pattern = re.compile(r"(?i)(api[_-]?key|secret|password|private[_-]?key)\\s*[:=]\\s*['\"][^'\"]{12,}")
    found = bool(secret_pattern.search(diff))
    status = "FAIL" if found else "PASS"
    result = update_role(
        manifest,
        "security_engineer",
        status,
        ["git diff secret-pattern scan"],
        "Potential credential pattern found" if found else "No credential pattern found; candidate remains subject to human review",
    )
    update_gates(manifest, no_secrets=not found)
    return {"status": status, "merge_allowed": result["gates"]["merge_allowed"]}


def stage_code_review():
    """Record deterministic diff hygiene; semantic review remains explicit."""
    print("=== STAGE 6: CODE REVIEW ===")
    manifest = _current_pr_manifest()
    if manifest is None:
        return {"status": "PENDING", "reason": "no current PR manifest"}
    _, _, diff_rc = run_cmd("git diff --check HEAD^..HEAD")
    status = "PASS" if diff_rc == 0 else "FAIL"
    result = update_role(
        manifest,
        "code_reviewer",
        status,
        ["git diff --check"],
        "Whitespace and patch hygiene passed; semantic review still required" if status == "PASS" else "Patch hygiene failed",
    )
    return {"status": status, "merge_allowed": result["gates"]["merge_allowed"]}


def stage_release():
    """Evaluate CI, cleanliness and release evidence without merging."""
    print("=== STAGE 7: DEVOPS/RELEASE REVIEW ===")
    manifest = _current_pr_manifest()
    if manifest is None:
        return {"status": "PENDING", "reason": "no current PR manifest"}
    pr_number = json.loads(run_cmd("gh pr view --repo stoltembergg-png/hermes-agent --json number")[0])["number"]
    checks_out, _, checks_rc = run_cmd(
        f"gh pr checks {pr_number} --repo stoltembergg-png/hermes-agent --json bucket,state,name"
    )
    try:
        checks = json.loads(checks_out) if checks_rc == 0 else []
    except json.JSONDecodeError:
        checks = []
    ci_green = bool(checks) and all(c.get("bucket") in {"pass", "skipping"} for c in checks)
    clean = not bool(run_cmd("git status --porcelain")[0].strip())
    result = update_gates(manifest, ci_green=ci_green, worktree_clean=clean)
    status = "PASS" if ci_green and clean else "PENDING"
    result = update_role(
        manifest,
        "devops_release_engineer",
        status,
        ["gh pr checks JSON", "git status --porcelain"],
        "CI green and worktree clean" if status == "PASS" else "Waiting for green CI and clean worktree",
    )
    return {"status": status, "ci_green": ci_green, "worktree_clean": clean, "merge_allowed": result["gates"]["merge_allowed"]}


# ============================================================
# STAGE 8: MERGE
# ============================================================
def stage_merge():
    """Merge only PRs approved by the manifest and fully green in GitHub."""
    print("=== STAGE 8: MERGE ===")
    results = {"merged": [], "skipped": []}
    out, _, rc = run_cmd(
        "gh pr list --repo stoltembergg-png/hermes-agent --state open "
        "--json number,title,isDraft --limit 20"
    )
    try:
        prs = json.loads(out) if rc == 0 else []
    except json.JSONDecodeError:
        prs = []

    for pr in prs:
        number = pr["number"]
        if pr.get("isDraft"):
            results["skipped"].append({"pr": number, "reason": "draft PR"})
            continue
        path = MANIFEST_DIR / f"pr-{number}.json"
        if not path.exists():
            results["skipped"].append({"pr": number, "reason": "manifest missing"})
            continue
        manifest = json.loads(path.read_text(encoding="utf-8"))
        checks_out, _, checks_rc = run_cmd(
            f"gh pr checks {number} --repo stoltembergg-png/hermes-agent --json bucket,state,name"
        )
        try:
            checks = json.loads(checks_out) if checks_rc == 0 else []
        except json.JSONDecodeError:
            checks = []
        ci_green = bool(checks) and all(c.get("bucket") in {"pass", "skipping"} for c in checks)
        manifest = update_gates(path, ci_green=ci_green)
        gate = merge_gate(manifest)
        if not gate["merge_allowed"]:
            results["skipped"].append({"pr": number, "reason": "; ".join(gate["reasons"])})
            print(f"  PR #{number}: skipped — {', '.join(gate['reasons'])}")
            continue
        _, _, merge_rc = run_cmd(
            f"gh pr merge {number} --repo stoltembergg-png/hermes-agent --squash --delete-branch",
            timeout=30,
        )
        if merge_rc == 0:
            results["merged"].append(number)
        else:
            results["skipped"].append({"pr": number, "reason": "GitHub merge command failed"})

    print(f"  Merged: {len(results['merged'])}, Skipped: {len(results['skipped'])}")
    return results


# ============================================================
# STAGE 5: FIX CI
# ============================================================
def stage_fix_ci():
    """Diagnose CI failures without switching or mutating another branch."""
    print("=== STAGE 9: FIX CI ===")
    out, _, rc = run_cmd(
        "gh pr list --repo stoltembergg-png/hermes-agent --state open "
        "--json number,title,headRefName --limit 20"
    )
    try:
        prs = json.loads(out) if rc == 0 else []
    except json.JSONDecodeError:
        prs = []
    results = {"failing": [], "action_required": []}
    for pr in prs:
        number = pr["number"]
        checks, _, check_rc = run_cmd(
            f"gh pr checks {number} --repo stoltembergg-png/hermes-agent --json bucket,state,name"
        )
        if check_rc != 0:
            results["action_required"].append({"pr": number, "reason": "could not read checks"})
            continue
        try:
            data = json.loads(checks)
        except json.JSONDecodeError:
            data = []
        failing = [item.get("name", "unknown") for item in data if item.get("bucket") == "fail"]
        if failing:
            results["failing"].append({"pr": number, "checks": failing})
            results["action_required"].append({"pr": number, "reason": "use isolated worktree for fix"})
    return results


# ============================================================
# STAGE 6: LEARN
# ============================================================
def stage_learn():
    """Better Harness analysis + skill updates."""
    print("=== STAGE 6: LEARN ===")
    results = {}

    # Run Better Harness
    out, err, rc = run_cmd(
        "better-harness harness analyze --workspace . --format json 2>&1 | python3 -c \"import sys,json; d=json.load(sys.stdin); e=d.get('lead',{}).get('data',{}).get('evidence',''); print(e[:2000])\"",
        timeout=60
    )
    if rc == 0:
        print(f"  Better Harness: analysis complete")
        results["harness"] = "complete"
    else:
        print(f"  Better Harness: {err[:100]}")
        results["harness"] = "error"

    # Update DESIGN.md if needed
    print("  Checking DESIGN.md...")
    design_path = Path(REPO) / "DESIGN.md"
    if design_path.exists():
        print("  DESIGN.md: exists")
        results["design_md"] = "exists"
    else:
        print("  DESIGN.md: missing")
        results["design_md"] = "missing"

    # Check skill freshness
    skills_dir = Path.home() / ".hermes" / "skills" / "software-development" / "vector-pr-checklist"
    if skills_dir.exists():
        print("  vector-pr-checklist skill: present")
        results["skill"] = "present"
    else:
        print("  vector-pr-checklist skill: missing")
        results["skill"] = "missing"

    # Check for recurring friction patterns
    print("  Checking for recurring CI friction...")
    out, _, _ = run_cmd(
        "gh run list --repo stoltembergg-png/hermes-agent --limit 10 --json conclusion,name --jq '.[] | select(.conclusion==\"failure\") | .name' 2>&1 | sort | uniq -c | sort -rn | head -5"
    )
    if out.strip():
        print(f"  Recurring failures: {out}")
        results["recurring_failures"] = out.strip()

    return results


# ============================================================
# MAIN
# ============================================================
def main():
    state = load_state()
    stage_idx = next_stage(state)
    stage_name = STAGES[stage_idx]

    print(f"\n{'='*60}")
    print(f"VECTOR PIPELINE — Cycle {state['cycle'] + 1}, Stage: {stage_name.upper()}")
    print(f"{'='*60}\n")

    if stage_name == "diagnose":
        result = stage_diagnose()
    elif stage_name == "orchestrate":
        result = stage_orchestrate()
    elif stage_name == "implement":
        result = stage_implement()
    elif stage_name == "lint_test":
        result = stage_lint_test()
    elif stage_name == "security_review":
        result = stage_security_review()
    elif stage_name == "code_review":
        result = stage_code_review()
    elif stage_name == "release":
        result = stage_release()
    elif stage_name == "merge":
        result = stage_merge()
    elif stage_name == "fix_ci":
        result = stage_fix_ci()
    elif stage_name == "learn":
        result = stage_learn()
    else:
        print(f"Unknown stage: {stage_name}")
        sys.exit(1)

    # Update state
    state["last_stage"] = stage_name
    state["last_run"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    if stage_idx == len(STAGES) - 1:
        state["cycle"] = state.get("cycle", 0) + 1
    save_state(state)

    print(f"\n{'='*60}")
    print(f"Stage complete: {stage_name}")
    print(f"Next stage: {STAGES[(stage_idx + 1) % len(STAGES)]}")
    print(f"{'='*60}\n")

    # Print result as JSON for the agent to consume
    print("RESULT:")
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
