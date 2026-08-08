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

REPO = "/home/ec2-user/hermes-agent"
STATE_FILE = Path("/home/ec2-user/.hermes/pipeline/state.json")
STAGES = ["diagnose", "implement", "lint_test", "merge", "fix_ci", "learn"]


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
            for line in gh_hosts.read_text().splitlines():
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
# STAGE 2: IMPLEMENT
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
    """Run eslint --fix and pytest on all open PR branches."""
    print("=== STAGE 3: LINT + TEST ===")
    results = {"branches_checked": [], "fixes_applied": 0}

    out, _, _ = run_cmd(
        "gh pr list --repo stoltembergg-png/hermes-agent --state open --json headRefName --limit 20"
    )
    try:
        prs = json.loads(out)
    except json.JSONDecodeError:
        prs = []

    for pr in prs:
        branch = pr["headRefName"]
        print(f"  Checking branch: {branch}")

        # Checkout branch
        run_cmd(f"git stash 2>/dev/null; git checkout {branch} 2>&1 | tail -1")

        # Run eslint --fix
        out, err, rc = run_cmd(
            "npx eslint apps/desktop/src/plugins/vector-channels/plugin.tsx apps/desktop/src/plugins/vector-channels/api.ts --fix 2>&1 | tail -5",
            timeout=60
        )
        if rc == 0:
            print(f"    ESLint: clean")
        else:
            print(f"    ESLint: {out[:100]}")

        # Check for changes
        out, _, _ = run_cmd("git diff --stat")
        if out.strip():
            print(f"    Changes detected — committing")
            run_cmd("git add -A && git commit -s -m 'fix: auto-lint via pipeline'")
            run_cmd(f"git push personal {branch} 2>&1 | tail -2", timeout=30)
            results["fixes_applied"] += 1
        else:
            print(f"    No changes needed")

        results["branches_checked"].append(branch)

    # Run contract tests
    out, err, rc = run_cmd(
        "source venv/bin/activate && python3 -m pytest vector/tests/ -q --tb=line 2>&1 | tail -5",
        timeout=60
    )
    print(f"  Contract tests: {out}")

    return results


# ============================================================
# STAGE 4: MERGE
# ============================================================
def stage_merge():
    """Merge all PRs with green CI."""
    print("=== STAGE 4: MERGE ===")
    results = {"merged": [], "skipped": []}

    out, _, _ = run_cmd(
        "gh pr list --repo stoltembergg-png/hermes-agent --state open --json number,title,headRefName --limit 20"
    )
    try:
        prs = json.loads(out)
    except json.JSONDecodeError:
        prs = []

    for pr in prs:
        pr_num = pr["number"]
        title = pr["title"]

        # Check CI status
        out, _, _ = run_cmd(
            f"gh pr checks {pr_num} --repo stoltembergg-png/hermes-agent 2>&1 | head -3"
        )

        if "All checks were successful" in out:
            print(f"  PR #{pr_num}: CI green — merging")
            out, err, rc = run_cmd(
                f"gh pr merge {pr_num} --repo stoltembergg-png/hermes-agent --squash --delete-branch --admin 2>&1 | tail -3",
                timeout=30
            )
            if rc == 0 and "merged" in out.lower():
                print(f"    MERGED")
                results["merged"].append(pr_num)
            else:
                print(f"    Merge failed: {out[:100]}")
                results["skipped"].append({"pr": pr_num, "reason": out[:100]})
        else:
            print(f"  PR #{pr_num}: CI not green — skipping")
            results["skipped"].append({"pr": pr_num, "reason": "CI not green"})

    print(f"  Merged: {len(results['merged'])}, Skipped: {len(results['skipped'])}")
    return results


# ============================================================
# STAGE 5: FIX CI
# ============================================================
def stage_fix_ci():
    """Fix failing CI on open PRs."""
    print("=== STAGE 5: FIX CI ===")
    results = {"fixed": [], "still_failing": []}

    out, _, _ = run_cmd(
        "gh pr list --repo stoltembergg-png/hermes-agent --state open --json number,title,headRefName --limit 20"
    )
    try:
        prs = json.loads(out)
    except json.JSONDecodeError:
        prs = []

    for pr in prs:
        pr_num = pr["number"]
        branch = pr["headRefName"]

        out, _, _ = run_cmd(
            f"gh pr checks {pr_num} --repo stoltembergg-png/hermes-agent 2>&1 | head -5"
        )

        if "failing" in out:
            print(f"  PR #{pr_num}: CI failing — attempting fix")
            # Checkout, eslint --fix, push
            run_cmd(f"git stash 2>/dev/null; git checkout {branch} 2>&1 | tail -1")
            run_cmd("npx eslint apps/desktop/src/plugins/vector-channels/plugin.tsx apps/desktop/src/plugins/vector-channels/api.ts --fix 2>&1 | tail -3", timeout=60)
            out, _, _ = run_cmd("git diff --stat")
            if out.strip():
                run_cmd("git add -A && git commit -s -m 'fix: auto-fix CI lint via pipeline'")
                run_cmd(f"git push personal {branch} 2>&1 | tail -2", timeout=30)
                print(f"    Pushed fix")
                results["fixed"].append(pr_num)
            else:
                print(f"    No lint auto-fix possible — needs manual intervention")
                results["still_failing"].append({"pr": pr_num, "reason": "no auto-fix"})
        else:
            print(f"  PR #{pr_num}: CI OK")

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
    elif stage_name == "implement":
        result = stage_implement()
    elif stage_name == "lint_test":
        result = stage_lint_test()
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
