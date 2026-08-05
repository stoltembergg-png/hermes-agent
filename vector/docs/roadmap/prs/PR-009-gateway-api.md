# PR-009 — Vector Gateway API + Service Layer

> Status: implemented
> Branch: `feature/pr-009-vector-gateway-api`
> Base: `main`

## Summary

Exposes the existing Vector domain (AgentRegistry, ChannelStore, AgentRuntime, Dispatcher)
through the local Hermes gateway REST surface under `/api/vector/*`. Adds a
VectorService composition layer, Pydantic schemas, FastAPI router, dispatcher
context fix, and hermetic E2E tests.

## Changes

### Backend

- `vector/src/vector/schemas.py` — 19 Pydantic models (request/response/error envelope)
- `vector/src/vector/service.py` — VectorService composition with DI, error mapping, persistence
- `vector/src/vector/api.py` — FastAPI router with 8 endpoints under `/api/vector`
- `vector/src/vector/runtime.py` — `context` parameter added to `run()`, combined with system_prompt
- `vector/src/vector/dispatcher.py` — passes `context_str` to `runtime.run()`
- `vector/src/vector/channel.py` — `check_same_thread=False` for TestClient compatibility
- `hermes_cli/web_server.py` — lazy router registration under `/api/vector`

### Desktop

- `apps/desktop/src/plugins/vector-channels/api.ts` — typed API client targeting `/api/vector/*`
- `apps/desktop/src/plugins/vector-channels/plugin.tsx` — migrated to use api.ts, data-testid selectors
- `apps/desktop/src/plugins/vector-channels/api.test.ts` — Vitest tests for API client
- `apps/desktop/src/plugins/vector-channels/plugin.test.ts` — updated for MessageInfo type

### Testing

- `vector/tests/test_pr_009_gateway_api.py` — 19 tests (6 ACs: health, persistence, post+dispatch, membership, context, errors)
- `vector/tests/test_pr_009_gateway_e2e.py` — 3 E2E tests (vertical slice, persistence, hermetic)

### CI

- `.github/workflows/vector-gateway-api.yml` — Python contract + desktop unit jobs

## API Contract

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/vector/health` | Service health |
| GET | `/api/vector/agents` | List agents |
| POST | `/api/vector/agents` | Create agent |
| GET | `/api/vector/channels` | List channels |
| POST | `/api/vector/channels` | Create channel |
| GET | `/api/vector/channels/{id}/members` | List members |
| GET | `/api/vector/channels/{id}/messages` | History |
| POST | `/api/vector/channels/{id}/messages` | Post + dispatch |

## Acceptance Criteria

- [x] AC-VEC-009-1: health endpoint
- [x] AC-VEC-009-2: persistence after recreation
- [x] AC-VEC-009-3: post stores + dispatches + stores response
- [x] AC-VEC-009-4: non-member mention not invoked
- [x] AC-VEC-009-5: context propagation
- [x] AC-VEC-009-6: stable error envelope
- [x] AC-VEC-009-7: response includes user + agent messages
- [x] AC-VEC-009-9: hermetic CI

## Test Commands

```bash
uv run ruff check vector/src vector/tests
uv run pytest vector/tests/test_pr_009_gateway_api.py vector/tests/test_pr_009_gateway_e2e.py -v
bash vector/scripts/verify-feature.sh pr-009-gateway-api --json
npm run --workspace apps/desktop typecheck
npm run --workspace apps/desktop lint
npm run --workspace apps/desktop test:ui
```

## Security

- Reuses existing gateway auth/origin policy
- Bounded message/channel/history limits
- No tracebacks in error responses
- Plugin remains disabled by default
