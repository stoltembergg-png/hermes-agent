# PR-014: Visible agent list in sidebar

## Depends on
PR-011

## Problem
The sidebar only shows channels. Registered agents are invisible unless the user opens the "Create Channel" modal (where they appear as toggle chips). There is no way to see which agents exist, what their system prompt is, or what model they use.

## Requirements

### REQ-VEC-014-1: Agent section in sidebar
The sidebar MUST have two sections: "Channels" (top) and "Agents" (bottom). Each section has a header with its title.

### REQ-VEC-014-2: Agent rows
Each agent row shows:
- Robot icon (Codicon `robot`)
- `@handle` (bold)
- Model name (muted, truncated — `--inherit--` or the model ID)
- A delete button (trash icon) on hover

### REQ-VEC-014-3: Health check for existing agents on load
On `ChannelsPage` mount, the existing `listAgents` call already fetches agents. Store the full agent objects (not just handles) in `$agentDetails` atom so the sidebar can show model info.

### REQ-VEC-014-4: Agent click shows details panel
Clicking an agent row opens a details panel in the main area (replacing channel view) showing:
- Handle
- System prompt (full text)
- Model + provider
- Channel memberships (which channels this agent belongs to)
- Delete agent button

## Acceptance Criteria

- AC-VEC-014-1: Sidebar shows "Agents" section below "Channels" with all registered agents
- AC-VEC-014-2: Each agent row shows handle + model name
- AC-VEC-014-3: Clicking an agent shows a details panel with system prompt and model info
- AC-VEC-014-4: Agent list updates when a new agent is created or deleted

## Implementation Plan

### Files
- `apps/desktop/src/plugins/vector-channels/plugin.tsx` (~+100 LoC)
- `apps/desktop/src/plugins/vector-channels/vector-channels.css` (~+40 LoC)

### Steps
1. Add `$agentDetails` atom — stores full `AgentInfo[]` (not just `string[]`)
2. Update `listAgents()` call in mount `useEffect` to `$agentDetails.set(agentList)`
3. Keep `$agents` as `$agentDetails.get().map(a => a.handle)` for backward compat with channel modal
4. Add `AgentRow` component — robot icon + handle + model + delete btn
5. Add `AgentDetails` component — full agent profile view in main area
6. Add `$selectedAgent` atom — when set, show `AgentDetails` instead of channel view
7. In sidebar, below channels, render `AgentRow` list
8. Add CSS for agent rows and details panel

test_file: tests/test_pr_014.py
