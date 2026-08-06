# PR-020: Edit agent profile (system prompt, model, provider)

## Depends on
PR-013, PR-014

## Problem
Once an agent is created, there is no way to edit its system prompt, model, or provider. Users must delete and recreate the agent to change any property — losing channel memberships in the process.

## Requirements

### REQ-VEC-020-1: PUT /agents/{handle}
Add `PUT /agents/{handle}` endpoint to `plugin_api.py` that:
- Accepts optional `system_prompt`, `model`, `provider`, `tools`, `fallback_models`
- Updates only the provided fields (partial update)
- Returns the updated `AgentOut`
- Throws `VECTOR_AGENT_NOT_FOUND` if handle doesn't exist

### REQ-VEC-020-2: Service layer update method
Add `AgentRegistry.update(handle: str, **fields)` — updates fields in the dataclass and saves to YAML. Only provided keyword arguments are applied.

### REQ-VEC-020-3: Edit button in AgentDetails
The AgentDetails panel MUST have an "Edit" button that switches to edit mode:
- System prompt: textarea (editable)
- Model: dropdown (same as AddAgentModal picker)
- Provider: dropdown
- Save button: calls `api.updateAgent(handle, {...})`
- Cancel button: reverts to view mode

### REQ-VEC-020-4: API client method
Add `updateAgent(handle: string, fields: Partial<AgentInfo>)` to `api.ts`.

## Acceptance Criteria

- AC-VEC-020-1: AgentDetails has "Edit" button that switches to edit mode
- AC-VEC-020-2: Editing system prompt and saving updates the agent profile
- AC-VEC-020-3: Editing model/provider and saving updates the agent profile
- AC-VEC-020-4: After save, agent list in sidebar shows the updated model name

## Implementation Plan

### Files
- `vector/src/vector/profile.py` (~+25 LoC)
- `plugins/vector-channels/dashboard/plugin_api.py` (~+30 LoC)
- `apps/desktop/src/plugins/vector-channels/api.ts` (~+15 LoC)
- `apps/desktop/src/plugins/vector-channels/plugin.tsx` (~+80 LoC)

### Steps
1. `profile.py`: Add `AgentRegistry.update(handle, **kwargs)`:
   - Get agent dataclass
   - For each kwarg, setattr if value is not None
   - Save to YAML
2. `service.py`: Add `update_agent(handle, **kwargs)` wrapping `registry.update`
3. `plugin_api.py`: Add `PUT /agents/{handle}` handler
4. `api.ts`: Add `updateAgent(handle, fields)` calling `rest('/agents/' + handle, { method: 'PUT', body: fields })`
5. `plugin.tsx`: In AgentDetails, add edit mode toggle
6. `plugin.tsx`: Edit mode shows textarea + dropdowns (reuse model picker from PR-013)
7. `plugin.tsx`: Save calls `updateAgent` → refresh `$agentDetails`

test_file: tests/test_pr_020.py
