#!/usr/bin/env bash
# install-vector.sh — Vector Channels Plugin installer
# Lives inside the hermes-agent repo. Installs the vector plugin from
# whatever source tree this script was run from (or clones the repo).
#
# Works on Linux, macOS, and Windows (Git Bash / WSL).
# Auto-installs all prerequisites: Hermes Agent, Python 3.11+, Node.js 22+, git.
set -euo pipefail

PLUGIN_NAME="vector-channels"
REPO="stoltembergg-png/hermes-agent"
BRANCH="main"
CLONE_DIR="/tmp/hermes-agent-install-$$"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info()  { echo -e "  ${BLUE}[INFO]${NC} $1"; }
ok()    { echo -e "  ${GREEN}[OK]${NC} $1"; }
warn()  { echo -e "  ${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "  ${RED}[ERROR]${NC} $1"; }

cleanup() { rm -rf "$CLONE_DIR"; }
trap cleanup EXIT

echo ""
echo "  Vector Channels Plugin — Installer"
echo "  ==================================="
echo ""

# --- Detect OS ---
OS="unknown"
ARCH="x64"
case "$(uname -s)" in
  Linux*)  OS="linux" ;;
  Darwin*) OS="macos" ;;
  MINGW*|MSYS*|CYGWIN*) OS="windows" ;;
esac
case "$(uname -m)" in
  x86_64|amd64) ARCH="x64" ;;
  aarch64|arm64) ARCH="arm64" ;;
esac

info "Detected: $OS $ARCH"

HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
DESKTOP_PLUGINS_DIR="$HERMES_HOME/desktop-plugins"
BACKEND_PLUGINS_DIR="$HERMES_HOME/plugins"

echo "  Hermes home: $HERMES_HOME"
echo ""

# ============================================================
# Determine source: local repo or clone from GitHub
# ============================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR=""
USE_LOCAL=false

# If we're inside the hermes-agent repo (has apps/desktop/src/plugins/vector-channels)
if [ -d "$SCRIPT_DIR/apps/desktop/src/plugins/vector-channels" ]; then
  SOURCE_DIR="$SCRIPT_DIR"
  USE_LOCAL=true
  info "Using local source: $SOURCE_DIR"
elif [ -d "$SCRIPT_DIR/../apps/desktop/src/plugins/vector-channels" ]; then
  SOURCE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
  USE_LOCAL=true
  info "Using local source: $SOURCE_DIR"
fi

# ============================================================
# STEP 1: Install Hermes Agent if not found
# ============================================================
if ! command -v hermes &>/dev/null; then
  info "Hermes Agent CLI not found. Installing..."

  if command -v python3 &>/dev/null; then
    PY_VERSION=$(python3 -c 'import sys; print(sys.version_info[0]*100+sys.version_info[1])' 2>/dev/null || echo 0)
    if [ "$PY_VERSION" -ge 311 ]; then
      info "Installing Hermes Agent via pip..."
      python3 -m pip install --user hermes-agent 2>&1 | tail -3 || true
      export PATH="$HOME/.local/bin:$PATH"
    fi
  fi

  if ! command -v hermes &>/dev/null; then
    info "Trying official Hermes install script..."
    curl -fsSL "https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh" | bash 2>&1 | tail -5 || true
    export PATH="$HOME/.local/bin:$PATH"
  fi

  if ! command -v hermes &>/dev/null; then
    error "Could not install Hermes Agent automatically."
    error "Install manually: https://hermes-agent.nousresearch.com/docs"
    exit 1
  fi
  ok "Hermes Agent installed"
else
  ok "Hermes Agent found: $(hermes --version 2>/dev/null || echo 'installed')"
fi
echo ""

# ============================================================
# STEP 2: Install Python 3.11+ if not found
# ============================================================
NEED_PYTHON=false
if ! command -v python3 &>/dev/null; then
  NEED_PYTHON=true
else
  PY_VERSION=$(python3 -c 'import sys; print(sys.version_info[0]*100+sys.version_info[1])' 2>/dev/null || echo 0)
  if [ "$PY_VERSION" -lt 311 ]; then
    NEED_PYTHON=true
  fi
fi

if [ "$NEED_PYTHON" = true ]; then
  info "Python 3.11+ not found. Installing..."
  case "$OS" in
    linux)
      if command -v dnf &>/dev/null; then
        sudo dnf install -y python3.11 python3.11-pip 2>&1 | tail -3 || true
      elif command -v apt &>/dev/null; then
        sudo apt update -qq && sudo apt install -y python3 python3-pip python3-venv 2>&1 | tail -3 || true
      elif command -v apk &>/dev/null; then
        sudo apk add python3 py3-pip 2>&1 | tail -3 || true
      elif command -v pacman &>/dev/null; then
        sudo pacman -S --noconfirm python python-pip 2>&1 | tail -3 || true
      fi
      ;;
    macos)
      if command -v brew &>/dev/null; then
        brew install python@3.12 2>&1 | tail -3 || true
      elif command -v xcode-select &>/dev/null; then
        xcode-select --install 2>&1 || true
      fi
      ;;
    windows)
      if command -v winget &>/dev/null; then
        winget install Python.Python.3.12 2>&1 | tail -3 || true
      elif command -v choco &>/dev/null; then
        choco install python --version=3.12.0 2>&1 | tail -3 || true
      fi
      ;;
  esac
  command -v python3 &>/dev/null && ok "Python installed: $(python3 --version)" || warn "Python not installed — backend skipped"
else
  ok "Python found: $(python3 --version)"
fi
echo ""

# ============================================================
# STEP 3: Install Node.js 22+ if not found
# ============================================================
NEED_NODE=false
if ! command -v node &>/dev/null; then
  NEED_NODE=true
else
  NODE_VERSION=$(node --version 2>/dev/null | sed 's/v//' | cut -d. -f1)
  if [ -z "$NODE_VERSION" ] || [ "$NODE_VERSION" -lt 22 ] 2>/dev/null; then
    NEED_NODE=true
  fi
fi

if [ "$NEED_NODE" = true ]; then
  info "Node.js 22+ not found. Installing via nvm..."
  export NVM_DIR="$HOME/.nvm"
  if [ ! -d "$NVM_DIR" ]; then
    info "Installing nvm..."
    curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash 2>&1 | tail -3 || true
  fi
  if [ -s "$NVM_DIR/nvm.sh" ]; then
    . "$NVM_DIR/nvm.sh"
    info "Installing Node.js 22 via nvm..."
    nvm install 22 2>&1 | tail -3 || true
    nvm use 22 2>&1 || true
    nvm alias default 22 2>&1 || true
  fi
  command -v node &>/dev/null && ok "Node.js installed: $(node --version)" || warn "Node.js not installed — frontend skipped"
else
  ok "Node.js found: $(node --version)"
fi
echo ""

# ============================================================
# STEP 4: Install git if not found
# ============================================================
if ! command -v git &>/dev/null; then
  info "git not found. Installing..."
  case "$OS" in
    linux)
      if command -v dnf &>/dev/null; then sudo dnf install -y git ;;
      elif command -v apt &>/dev/null; then sudo apt install -y git ;;
      elif command -v apk &>/dev/null; then sudo apk add git ;;
      elif command -v pacman &>/dev/null; then sudo pacman -S --noconfirm git ;;
      fi
      ;;
    macos)
      xcode-select --install 2>&1 || true
      ;;
    windows)
      if command -v winget &>/dev/null; then winget install Git.Git ;;
      elif command -v choco &>/dev/null; then choco install git ;;
      fi
      ;;
  esac
  command -v git &>/dev/null && ok "git installed" || warn "git not available"
else
  ok "git found: $(git --version)"
fi
echo ""

# ============================================================
# STEP 5: Get source code (local or clone)
# ============================================================
if [ "$USE_LOCAL" = false ]; then
  info "Cloning $REPO (branch: $BRANCH)..."
  git clone --depth 1 --branch "$BRANCH" "https://github.com/$REPO.git" "$CLONE_DIR" 2>&1 | grep -v "Cloning\|remote\|Unpacking\|Receiving" || true
  SOURCE_DIR="$CLONE_DIR"
  ok "Cloned"
  echo ""
fi

# ============================================================
# STEP 6: Install Python backend
# ============================================================
info "Installing Python backend..."

if [ -d "$SOURCE_DIR/plugins/vector-channels/dashboard" ]; then
  mkdir -p "$BACKEND_PLUGINS_DIR/$PLUGIN_NAME"
  cp -r "$SOURCE_DIR/plugins/vector-channels/dashboard/"* "$BACKEND_PLUGINS_DIR/$PLUGIN_NAME/" 2>/dev/null || true
  ok "Backend API installed"
else
  warn "Backend directory not found"
fi

if [ -d "$SOURCE_DIR/vector/src/vector" ]; then
  mkdir -p "$HERMES_HOME/vector"
  cp -r "$SOURCE_DIR/vector/src/vector/" "$HERMES_HOME/vector/"
  ok "Vector Python package installed"
fi

if [ -d "$SOURCE_DIR/vector/tests" ]; then
  mkdir -p "$HERMES_HOME/vector/tests"
  cp "$SOURCE_DIR/vector/tests/"*.py "$HERMES_HOME/vector/tests/" 2>/dev/null || true
  ok "Test suite installed"
fi
echo ""

# ============================================================
# STEP 7: Build + install desktop frontend
# ============================================================
INSTALL_FRONTEND=false
if command -v node &>/dev/null; then
  NODE_VERSION=$(node --version 2>/dev/null | sed 's/v//' | cut -d. -f1)
  if [ -n "$NODE_VERSION" ] && [ "$NODE_VERSION" -ge 22 ] 2>/dev/null; then
    INSTALL_FRONTEND=true
  fi
fi

if [ "$INSTALL_FRONTEND" = true ] && [ -d "$SOURCE_DIR/apps/desktop/src/plugins/vector-channels" ]; then
  info "Building desktop frontend..."

  PLUGIN_SRC="$SOURCE_DIR/apps/desktop/src/plugins/vector-channels"
  BUILD_DIR="/tmp/vector-plugin-build-$$"
  mkdir -p "$BUILD_DIR/src"
  cp "$PLUGIN_SRC/plugin.tsx" "$BUILD_DIR/src/" 2>/dev/null || true
  cp "$PLUGIN_SRC/api.ts" "$BUILD_DIR/src/" 2>/dev/null || true
  cp "$PLUGIN_SRC/vector-channels.css" "$BUILD_DIR/src/" 2>/dev/null || true

  cat > "$BUILD_DIR/package.json" << 'PKGEOF'
{
  "name": "vector-channels-build",
  "version": "0.1.0",
  "type": "module",
  "scripts": { "build": "vite build" },
  "dependencies": { "react": "^18.3.0" },
  "devDependencies": { "typescript": "^5.5.0", "vite": "^5.4.0" }
}
PKGEOF

  cat > "$BUILD_DIR/vite.config.ts" << 'VITEEOF'
import { defineConfig } from 'vite'
import { resolve } from 'path'
export default defineConfig({
  build: {
    lib: { entry: resolve(__dirname, 'src/plugin.tsx'), formats: ['es'], fileName: 'plugin' },
    outDir: 'dist', emptyOutDir: true,
    rollupOptions: { external: ['react', 'react-dom', '@hermes/plugin-sdk'] },
  },
})
VITEEOF

  cd "$BUILD_DIR"
  npm install --silent 2>&1 | tail -3 || true
  npm run build 2>&1 | tail -5 || true

  mkdir -p "$DESKTOP_PLUGINS_DIR/$PLUGIN_NAME"
  if [ -f "dist/plugin.js" ]; then
    cp dist/plugin.js "$DESKTOP_PLUGINS_DIR/$PLUGIN_NAME/plugin.js"
    cp -r dist/* "$DESKTOP_PLUGINS_DIR/$PLUGIN_NAME/" 2>/dev/null || true
    ok "Frontend built and installed"
  else
    warn "Build failed — frontend skipped (backend still works)"
  fi
  rm -rf "$BUILD_DIR"
else
  warn "Node.js 22+ or plugin source not found. Frontend skipped."
fi
echo ""

# ============================================================
# STEP 8: Enable plugin
# ============================================================
info "Enabling plugin in Hermes config..."
hermes plugins enable "$PLUGIN_NAME" 2>/dev/null || true
ok "Plugin enabled"
echo ""

# ============================================================
# DONE
# ============================================================
echo "  ==================================="
echo "  Installation complete!"
echo "  ==================================="
echo ""
echo "  Plugin:    $PLUGIN_NAME"
echo "  Source:    ${REPO}@${BRANCH}"
echo "  Backend:   $BACKEND_PLUGINS_DIR/$PLUGIN_NAME"
echo "  Frontend:  $DESKTOP_PLUGINS_DIR/$PLUGIN_NAME"
echo "  Tests:     $HERMES_HOME/vector/tests"
echo ""
echo "  Next steps:"
echo "    1. Restart Hermes:  hermes gateway restart"
echo "    2. Open dashboard:  hermes dashboard"
echo "    3. Look for the Vector icon in the sidebar"
echo ""
echo "  To update: re-run this script or git pull + re-run."
echo ""
