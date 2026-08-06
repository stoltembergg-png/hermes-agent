# PR-013: Provider/model picker in Add Agent modal

## Depends on
PR-012

## Problem
The AddAgentModal only collects `handle` and `system_prompt`. The backend `CreateAgentRequest` schema already supports `model`, `provider`, `tools`, and `fallback_models` fields — but the UI doesn't expose them. Users cannot configure individual agent models.

## Requirements

### REQ-VEC-013-1: Model catalog endpoint
The API client (`api.ts`) MUST fetch the model catalog from the existing Hermes backend endpoint `/api/model/options` (which returns available providers and models).

### REQ-VEC-013-2: Provider dropdown
AddAgentModal MUST include a provider `<select>` dropdown populated from the model catalog. Options: all providers returned by `/api/model/options`. Default: empty (meaning "Inherit from session").

### REQ-VEC-013-3: Model dropdown
AddAgentModal MUST include a model `<select>` dropdown populated based on the selected provider. When provider is empty (inherit), show all models. Default: empty (meaning "Inherit from session").

### REQ-VEC-013-4: Pass model/provider to API
When the user selects a provider or model, `createAgent` MUST include them in the request body. When left empty, they MUST be omitted (backend will use session defaults).

### REQ-VEC-013-5: Collapsible advanced section
Provider/model selectors SHOULD be inside a "Advanced" collapsible `<details>` element so the base form stays simple (handle + system prompt).

## Acceptance Criteria

- AC-VEC-013-1: AddAgentModal has a provider dropdown populated from `/api/model/options`
- AC-VEC-013-2: Selecting a provider filters the model dropdown to that provider's models
- AC-VEC-013-3: Created agent has the selected `model` and `provider` fields in the backend
- AC-VEC-013-4: Leaving provider/model empty creates an agent with null model/provider (inherits session)
- AC-VEC-013-5: Advanced section is collapsed by default

## Implementation Plan

### Files
- `apps/desktop/src/plugins/vector-channels/api.ts` (~+40 LoC)
- `apps/desktop/src/plugins/vector-channels/plugin.tsx` (~+120 LoC)

### Steps
1. In `api.ts`, add `getModelOptions(): Promise<ModelOptions>` calling `rest('/api/model/options')` — this is a CORE Hermes endpoint, NOT under `/api/plugins/vector-channels/`, so it needs a different call path (use the `host.api` capability directly or add `restAbsolute`)
2. Actually — `/api/model/options` is a core endpoint. Check if `ctx.rest` can reach it by using path `../model/options` (relative escape) — likely NOT. Need to use `host.fetch` or similar SDK capability for absolute paths.
3. Add `ModelOptions` type: `{ providers: { name: string, models: string[] }[] }`
4. In AddAgentModal, add `<details><summary>Advanced</summary>` with provider + model selects
5. Fetch model catalog on modal mount via `useEffect`
6. On provider change, filter model options
7. Pass `model` and `provider` to `createAgent()` only if non-empty
8. Update `createAgent` in `api.ts` to accept and send optional `model`, `provider` fields

### Pitfall
The `ctx.rest` namespace constraint means we CANNOT reach `/api/model/options` through `ctx.rest('/api/model/options')` — it would become `/api/plugins/vector-channels/api/model/options`. We need either:
- (a) A `plugin_api.py` proxy: `GET /models` that calls the Hermes model options internally and returns it
- (b) A different SDK capability for absolute API paths
Option (a) is safer and follows the plugin pattern. Add `GET /models` to `plugin_api.py` that `$get_service()` is NOT needed for — just call the Hermes model resolver directly.

test_file: tests/test_pr_013.py
