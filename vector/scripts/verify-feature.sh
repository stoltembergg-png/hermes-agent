#!/usr/bin/env bash
# verify-feature.sh — Run the contract test for a feature and emit JSON
# evidence mapping each `@spec:AC-VEC-NNN-N` tag to a pass/fail status.
#
# Strategy (simplified, marker-driven):
#   1. Each test carries a `@pytest.mark.ac_vec_NNN_N` marker naming
#      the AC it satisfies. Strict-marker mode rejects typos.
#   2. We derive the spec AC list from .spec/features/<slug>/spec.md.
#   3. We use `pytest --collect-only -m ac_vec_NNN_N` to confirm each
#      AC has at least one collected test (presence check).
#   4. We run `pytest -m ac_vec_NNN_N` to confirm each AC passes.
#
# Usage:
#   sh scripts/verify-feature.sh <feature-slug> [--json] [--out PATH]
#
# Exit codes:
#   0  all ACs from the spec are present and pass
#   1  one or more ACs are missing from the test run
#   2  one or more ACs fail
#   3  internal error (bad arguments, missing spec, missing tests)

set -e

# ---- arg parsing -----------------------------------------------------------

FEATURE_SLUG=""
JSON_OUT=""
JSON_MODE=false
PYTEST_ARGS=()

while [ $# -gt 0 ]; do
    case "$1" in
        --json)
            JSON_MODE=true
            shift
            ;;
        --out)
            JSON_OUT="$2"
            shift 2
            ;;
        -h|--help)
            sed -n '2,30p' "$0"
            exit 0
            ;;
        *)
            if [ -z "$FEATURE_SLUG" ]; then
                FEATURE_SLUG="$1"
            else
                PYTEST_ARGS+=("$1")
            fi
            shift
            ;;
    esac
done

if [ -z "$FEATURE_SLUG" ]; then
    echo "usage: $0 <feature-slug> [--json] [--out PATH]" >&2
    exit 3
fi

# ---- bootstrap venv if missing ---------------------------------------------
#
# This script is invoked from the project root (`vector/scripts/`). It
# expects a `REPO_ROOT` that is the git toplevel (i.e. the monorepo
# hermes-agent/, not vector/ itself). All vector-local paths are derived
# from SCRIPT_DIR so the script works regardless of cwd.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VECTOR_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(git -C "$VECTOR_DIR" rev-parse --show-toplevel)"
SPEC_FILE="$VECTOR_DIR/.spec/features/$FEATURE_SLUG/spec.md"
UV="${UV:-uv}"

# Cross-platform venv Python path: Windows uses Scripts/, POSIX uses bin/.
# The venv lives inside vector/.venv/ so it doesn't pollute the monorepo.
if [ -x "$VECTOR_DIR/.venv/Scripts/python.exe" ]; then
    PYTEST="$VECTOR_DIR/.venv/Scripts/python.exe"
elif [ -x "$VECTOR_DIR/.venv/bin/python" ]; then
    PYTEST="$VECTOR_DIR/.venv/bin/python"
else
    PYTEST=""
fi

if [ -z "$PYTEST" ]; then
    if ! command -v "$UV" >/dev/null 2>&1; then
        echo "error: venv missing at $VECTOR_DIR/.venv/ and '$UV' is not on PATH" >&2
        echo "hint: install uv (https://docs.astral.sh/uv/) and re-run" >&2
        exit 3
    fi
    echo ">>> bootstrapping venv via uv …" >&2
    ( cd "$VECTOR_DIR" && "$UV" venv --python 3.11 .venv >/dev/null ) \
        || { echo "error: uv venv creation failed" >&2; exit 3; }
    # Re-detect path after bootstrap.
    if [ -x "$VECTOR_DIR/.venv/Scripts/python.exe" ]; then
        PYTEST="$VECTOR_DIR/.venv/Scripts/python.exe"
        ( cd "$VECTOR_DIR" && "$UV" pip install --python "$PYTEST" pytest pyyaml fastapi pydantic httpx httpx2 >/dev/null ) \
            || { echo "error: uv pip install failed" >&2; exit 3; }
    else
        PYTEST="$VECTOR_DIR/.venv/bin/python"
        ( cd "$VECTOR_DIR" && "$UV" pip install --python "$PYTEST" pytest pyyaml fastapi pydantic httpx httpx2 >/dev/null ) \
            || { echo "error: uv pip install failed" >&2; exit 3; }
    fi
fi

# Honour a `test_file:` declaration in spec.md if present; otherwise
# default to vector/tests/test_<slug>.py. The declaration, when used,
# is relative to VECTOR_DIR (the script's parent), not REPO_ROOT.
DECLARED_TEST_FILE=$(grep -E '^[ \t]*test_file:[ \t]*' "$SPEC_FILE" | head -1 | sed -E 's/^[ \t]*test_file:[ \t]*//' | tr -d '
')
if [ -n "$DECLARED_TEST_FILE" ]; then
    TEST_FILE="$VECTOR_DIR/$DECLARED_TEST_FILE"
else
    TEST_FILE="$VECTOR_DIR/tests/test_${FEATURE_SLUG}.py"
fi

# ---- preflight -------------------------------------------------------------

if [ ! -f "$SPEC_FILE" ]; then
    echo "error: spec file not found: $SPEC_FILE" >&2
    exit 3
fi
if [ ! -f "$TEST_FILE" ]; then
    echo "error: contract test file not found: $TEST_FILE" >&2
    exit 3
fi
if [ ! -x "$PYTEST" ]; then
    echo "error: venv python not found at $PYTEST" >&2
    exit 3
fi

# ---- collect ACs declared in the spec --------------------------------------

SPEC_ACS=$(grep -oE 'AC-VEC-[0-9]+-[0-9]+' "$SPEC_FILE" | sort -u)
SPEC_ACS_COUNT=$(echo "$SPEC_ACS" | grep -c . || true)

if [ "$SPEC_ACS_COUNT" -eq 0 ]; then
    echo "error: no AC tags found in spec file $SPEC_FILE" >&2
    exit 3
fi

# ---- derive AC markers -----------------------------------------------------

# ac_vec_001_1 -> AC-VEC-001-1
ac_to_marker() {
    echo "$1" | tr '[:upper:]' '[:lower:]' | sed -E 's/^ac-vec-/ac_vec_/' | tr '-' '_'
}
marker_to_ac() {
    echo "$1" | sed -E 's/^ac_vec_/AC-VEC-/' | tr '_' '-'
}

# ---- run contract test (only marked tests) ---------------------------------

# We restrict pytest to the marked tests so non-contract tests in the
# file (regression guards) don't affect the pass/fail count for the
# spec ACs.
MARK_EXPR=""
for ac in $SPEC_ACS; do
    m=$(ac_to_marker "$ac")
    if [ -z "$MARK_EXPR" ]; then
        MARK_EXPR="$m"
    else
        MARK_EXPR="$MARK_EXPR or $m"
    fi
done

PYTEST_LOG=$(mktemp)
trap 'rm -f "$PYTEST_LOG"' EXIT

# When running in human mode we want the pytest output on stdout so the
# user sees what's happening. When emitting JSON we want clean JSON
# only on stdout — pytest output goes to stderr.
if $JSON_MODE; then
    set +e
    ( cd "$REPO_ROOT" && PYTHONPATH="$VECTOR_DIR/src:$PYTHONPATH" "$PYTEST" -m pytest -m "$MARK_EXPR" "$TEST_FILE" -v --tb=short "${PYTEST_ARGS[@]}" ) \
        > "$PYTEST_LOG" 2>&1
    PYTEST_EXIT=$?
    set -e
else
    set +e
    ( cd "$REPO_ROOT" && PYTHONPATH="$VECTOR_DIR/src:$PYTHONPATH" "$PYTEST" -m pytest -m "$MARK_EXPR" "$TEST_FILE" -v --tb=short "${PYTEST_ARGS[@]}" ) 2>&1 | tee "$PYTEST_LOG"
    PYTEST_EXIT=${PIPESTATUS[0]}
    set -e
fi

# ---- collect results per AC ------------------------------------------------

# For each AC, run a focused pytest and observe the exit code. This is
# the cleanest way to attribute pass/fail to a specific AC marker
# without parsing free-form pytest output.
declare -A AC_STATUS
for ac in $SPEC_ACS; do
    m=$(ac_to_marker "$ac")
    set +e
    ( cd "$REPO_ROOT" && "$PYTEST" -m pytest -m "$m" "$TEST_FILE" --tb=no -q "${PYTEST_ARGS[@]}" ) >/dev/null 2>&1
    rc=$?
    set -e
    if [ "$rc" -eq 0 ]; then
        AC_STATUS["$ac"]="pass"
    elif [ "$rc" -eq 5 ]; then
        # pytest exit 5 = no tests collected
        AC_STATUS["$ac"]="missing"
    else
        AC_STATUS["$ac"]="fail"
    fi
done

# ---- aggregate -------------------------------------------------------------

PASSED_COUNT=0
FAILED_COUNT=0
MISSING_COUNT=0
DETAILS_JSON="["
FIRST=true
for ac in $SPEC_ACS; do
    status="${AC_STATUS[$ac]}"
    case "$status" in
        pass) PASSED_COUNT=$((PASSED_COUNT + 1)) ;;
        fail) FAILED_COUNT=$((FAILED_COUNT + 1)) ;;
        missing) MISSING_COUNT=$((MISSING_COUNT + 1)) ;;
    esac
    if $FIRST; then FIRST=false; else DETAILS_JSON="$DETAILS_JSON ,"; fi
    DETAILS_JSON="$DETAILS_JSON {\"ac\": \"$ac\", \"status\": \"$status\"}"
done
DETAILS_JSON="$DETAILS_JSON ]"

OVERALL_STATUS="pass"
EXIT_CODE=0
if [ "$FAILED_COUNT" -gt 0 ]; then
    OVERALL_STATUS="fail"
    EXIT_CODE=2
fi
if [ "$MISSING_COUNT" -gt 0 ]; then
    OVERALL_STATUS="fail"
    if [ "$EXIT_CODE" -eq 0 ]; then EXIT_CODE=1; fi
fi

# ---- emit output -----------------------------------------------------------

GIT_SHA=$(git rev-parse HEAD)
GIT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
GIT_DIRTY=$(git diff --quiet HEAD 2>/dev/null && echo "false" || echo "true")
PYTHON_VERSION=$("$PYTEST" --version 2>&1 | head -1)
PYTEST_VERSION=$("$PYTEST" -m pytest --version 2>&1 | head -1)
PLATFORM=$(uname -srm 2>/dev/null || echo "windows-amd64")

if $JSON_MODE; then
    cat <<EOF
{
  "feature": "$FEATURE_SLUG",
  "status": "$OVERALL_STATUS",
  "exit_code": $EXIT_CODE,
  "pytest_exit_code": $PYTEST_EXIT,
  "git": {
    "sha": "$GIT_SHA",
    "branch": "$GIT_BRANCH",
    "dirty": $GIT_DIRTY
  },
  "platform": "$PLATFORM",
  "tools": {
    "python": "$PYTHON_VERSION",
    "pytest": "$PYTEST_VERSION"
  },
  "spec_file": ".spec/features/$FEATURE_SLUG/spec.md",
  "test_file": "${DECLARED_TEST_FILE:-tests/test_${FEATURE_SLUG}.py}",
  "marker_expression": "$MARK_EXPR",
  "summary": {
    "spec_ac_count": $SPEC_ACS_COUNT,
    "passed_count": $PASSED_COUNT,
    "failed_count": $FAILED_COUNT,
    "missing_count": $MISSING_COUNT
  },
  "details": $DETAILS_JSON
}
EOF
    if [ -n "$JSON_OUT" ]; then
        # Write JSON to the requested path. Re-emit to stdout after.
        "$0" "$FEATURE_SLUG" --json > "$JSON_OUT" 2>/dev/null
        cat "$JSON_OUT"
    fi
else
    echo
    echo "=== verify-feature.sh summary ==="
    echo "feature:        $FEATURE_SLUG"
    echo "status:         $OVERALL_STATUS"
    echo "spec ACs:       $SPEC_ACS_COUNT"
    echo "passed:         $PASSED_COUNT"
    echo "failed:         $FAILED_COUNT"
    echo "missing:        $MISSING_COUNT"
    echo
    echo "Per-AC status:"
    for ac in $SPEC_ACS; do
        printf "  %-15s %s\n" "$ac" "${AC_STATUS[$ac]}"
    done
fi

exit $EXIT_CODE
