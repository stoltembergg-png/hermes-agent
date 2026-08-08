"""Tests for reproducible baseline scoring."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "pipeline"))

from create_baseline import score


def test_baseline_score_uses_only_reproducible_dimensions():
    assert score(
        {
            "tests_green": True,
            "lint_green": True,
            "security_green": True,
            "ci_green": True,
            "worktree_clean": True,
            "no_secrets": True,
        }
    ) == 100
    assert score({"tests_green": True, "security_green": True}) == 45


def test_unknown_dimensions_do_not_add_points():
    assert score({"agent_claimed_quality": True}) == 0
