# PR-012: Error parsing + clean error display

## Depends on
PR-011

## Problem
When agent creation fails (e.g. duplicate handle), the catch block shows the raw error string: `Error: 400: {"error":{"code":"VECTOR_BAD_REQUEST","message":"Agent 'gandalf' already exists","retryable":false}}`. Users see JSON instead of a clean message.

## Requirements

### REQ-VEC-012-1: Error envelope parsing
The API client (`api.ts`) MUST parse error responses with shape `{"error":{"code":"...","message":"...","retryable":...}}` and throw an `Error` whose `.message` is only the `message` field.

### REQ-VEC-012-2: Clean error in modals
`CreateChannelModal` and `AddAgentModal` MUST display the parsed error message (not raw JSON) in the `vector-modal-error` element.

### REQ-VEC-012-3: Error code suffix
When the error code is `VECTOR_BAD_REQUEST` and `retryable: false`, the modal error SHOULD show the message followed by a hint: "This action cannot be retried — try a different value."

### REQ-VEC-012-4: Network error messaging
When the REST call fails with a connection error (not an HTTP error response), the modal MUST show "Cannot reach the Hermes backend. Is it running?" instead of a stack trace.

## Acceptance Criteria

- AC-VEC-012-1: Creating agent with duplicate handle shows "Agent 'gandalf' already exists" (not JSON)
- AC-VEC-012-2: Creating channel with duplicate name shows clean error message
- AC-VEC-012-3: `retryable: false` errors show the retry hint
- AC-VEC-012-4: Backend offline shows "Cannot reach the Hermes backend. Is it running?"

## Implementation Plan

### Files
- `apps/desktop/src/plugins/vector-channels/api.ts` (~+30 LoC)
- `apps/desktop/src/plugins/vector-channels/plugin.tsx` (~+10 LoC)
- `apps/desktop/src/plugins/vector-channels/api.test.ts` (~+20 LoC)

### Steps
1. In `api.ts`, add `parseApiError(e: unknown): string` function:
   - Try `JSON.parse` on the error message substring after `: ` separator
   - If parsed has `.error.message`, return that
   - If `retryable === false`, append "\n\nThis action cannot be retried."
   - If JSON parse fails, check for network error keywords → return backend message
   - Fallback: return `e instanceof Error ? e.message : String(e)`
2. Export `parseApiError` from `api.ts`
3. In `plugin.tsx`, replace `e instanceof Error ? e.message : '...'` with `parseApiError(e)` in both modals
4. Add tests in `api.test.ts` for `parseApiError` with various error shapes
