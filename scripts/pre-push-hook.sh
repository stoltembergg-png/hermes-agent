#!/usr/bin/env bash
# Pre-push hook: auto-fix ESLint on Vector plugin files
# Install: cp this to .git/hooks/pre-push && chmod +x

set -e

REPO_ROOT=$(git rev-parse --show-toplevel)
PLUGIN_DIR="$REPO_ROOT/apps/desktop/src/plugins/vector-channels"

if [ ! -d "$PLUGIN_DIR" ]; then
    exit 0
fi

echo "[pre-push] Running ESLint --fix on Vector plugin files..."

cd "$REPO_ROOT"

# Check if npx is available
if command -v npx &>/dev/null; then
    npx eslint "$PLUGIN_DIR/plugin.tsx" "$PLUGIN_DIR/api.ts" --fix 2>/dev/null || true
    # Stage any fixes
    git add "$PLUGIN_DIR/plugin.tsx" "$PLUGIN_DIR/api.ts" 2>/dev/null || true
    echo "[pre-push] ESLint --fix complete"
else
    echo "[pre-push] npx not found, skipping ESLint check"
fi

# Run contract tests if pytest is available
if command -v python3 &>/dev/null && [ -d "$REPO_ROOT/vector/tests" ]; then
    echo "[pre-push] Running contract tests..."
    python3 -m pytest "$REPO_ROOT/vector/tests/" -q --tb=line 2>/dev/null || {
        echo "[pre-push] WARNING: Some contract tests failed"
    }
    echo "[pre-push] Tests complete"
fi

exit 0
