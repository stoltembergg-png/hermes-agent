# Vector Plugin Architecture

## Overview

Vector is a multi-agent orchestration layer built as a plugin for Hermes Agent. It adds multi-agent conversation channels, agent management, and model routing to the Hermes desktop app.

## Components

### Backend (Python)
- `plugins/vector-channels/` — Plugin entry point, registered via Hermes plugin system
- `plugins/vector-channels/dashboard/plugin_api.py` — REST API with FastAPI: channels CRUD, agents CRUD, messages, members, health, model options
- `vector/tests/` — Contract tests for each PR (test_pr_013.py through test_pr_024.py)

### Frontend (TypeScript/React)
- `apps/desktop/src/plugins/vector-channels/api.ts` — API client with all endpoints (listChannels, createChannel, deleteChannel, postMessage, createAgent, deleteAgent, getMembers, etc.)
- `apps/desktop/src/plugins/vector-channels/plugin.tsx` — React UI: sidebar with channels/agents list, chat panel with message history, channel/agent creation
- `apps/desktop/src/plugins/vector-channels/vector-channels.css` — Styling

### Infrastructure
- `.github/workflows/ci.yml` — CI pipeline with lint, contract tests, review bot
- `scripts/install-vector.sh` — Cross-platform installer
- `scripts/ci/` — CI review comment assembly, live comment, timing report
- `scripts/pre-push-hook.sh` — Pre-push hook with eslint --fix and pytest

## PR Roadmap

| PR | Title | Status |
|----|-------|--------|
| PR-013 (#27) | Channel list + chat panel | Merged |
| PR-014 (#30) | Agent list in sidebar | Merged |
| PR-015 (#33) | Model selection dropdown | CI failing |
| PR-016 (#32) | Delete backend endpoints | Merged |
| PR-017 | Delete frontend (trash buttons) | Local, 95% done |
| PR-018 | Channel member list + add/remove | Needs implementation |
| PR-019 (#35) | Message timestamps + author avatars | Merged |
| PR-020-024 | TBD (streaming, search, notifications, theming, export) | Not started |

## Conventions

- **ESLint perfectionist**: imports alphabetical, JSX props className-before-key
- **Tests**: contract tests in `vector/tests/` with pytest markers
- **CI**: must be green before merge, branch protection on `main`
- **No emojis** in CI review bot output
- **Pre-push hook**: `eslint --fix` + `pytest` before every push
- **Skill**: `vector-pr-checklist` — run before every Vector PR push

## Architecture Diagram

```
+-------------------+     +-------------------+
|   Desktop App     |     |   Hermes Core     |
|   (Electron)      |     |   (Python)        |
|                   |     |                   |
|  +-------------+  |     |  +-------------+  |
|  | Vector UI   |  |     |  | Vector API  |  |
|  | (plugin.tsx)|--|-----|->| (plugin_   |  |
|  |             |  | HTTP|  |  api.py)    |  |
|  +-------------+  |     |  +-------------+  |
|  | API Client  |  |     |  | FastAPI     |  |
|  | (api.ts)    |  |     |  | REST endpoints| |
|  +-------------+  |     |  +-------------+  |
+-------------------+     +-------------------+
                                |
                                v
                          +-------------+
                          | SQLite DB   |
                          | (channels,  |
                          |  agents,    |
                          |  messages)  |
                          +-------------+
```
