# PR-017: Delete agent + delete channel (frontend)

## Depends on
PR-016

## Problem
The backend now supports delete operations (PR-016), but the UI has no delete buttons. Users cannot remove agents or channels from the desktop interface.

## Requirements

### REQ-VEC-017-1: Delete agent button
Agent rows in the sidebar MUST show a trash icon (Codicon `trash`) on hover. Clicking it opens a confirmation modal:
- Title: "Delete @<handle>?"
- Body: "This will remove @<handle> from all channels. Their posted messages will be kept. This cannot be undone."
- Buttons: Cancel / Delete (red)

### REQ-VEC-017-2: Delete channel button
The channel header (in the message area) MUST show a trash icon. Clicking opens confirmation:
- Title: "Delete #<channel_name>?"
- Body: "This will permanently delete the channel, all messages, and all memberships. This cannot be undone."
- Buttons: Cancel / Delete (red)

### REQ-VEC-017-3: API client methods
Add to `api.ts`:
- `deleteAgent(handle: string): Promise<void>`
- `deleteChannel(channelId: string): Promise<void>`

### REQ-VEC-017-4: Post-delete UI refresh
After deleting an agent:
- Refresh `$agentDetails` list
- If the deleted agent's details panel was open, close it (set `$selectedAgent` to null)
After deleting a channel:
- Refresh `$channels` list
- Set `$activeChannel` to null (close the channel view)
- Clear `$messages` and `$members`

### REQ-VEC-017-5: Confirmation modal component
Add a reusable `ConfirmModal` component:
- Props: `title`, `message`, `confirmLabel`, `cancelLabel`, `onConfirm`, `onCancel`
- Used by both delete agent and delete channel

## Acceptance Criteria

- AC-VEC-017-1: Hovering an agent row shows a trash icon
- AC-VEC-017-2: Clicking trash on agent opens confirmation modal with agent name
- AC-VEC-017-3: Confirming agent deletion removes the agent from the sidebar list
- AC-VEC-017-4: Channel header has trash icon; clicking opens confirmation
- AC-VEC-017-5: Confirming channel deletion removes channel from sidebar and closes the view

## Implementation Plan

### Files
- `apps/desktop/src/plugins/vector-channels/api.ts` (~+15 LoC)
- `apps/desktop/src/plugins/vector-channels/plugin.tsx` (~+120 LoC)
- `apps/desktop/src/plugins/vector-channels/vector-channels.css` (~+30 LoC)

### Steps
1. `api.ts`: Add `deleteAgent(handle)` calling `rest('/agents/' + handle, { method: 'DELETE' })`
2. `api.ts`: Add `deleteChannel(channelId)` calling `rest('/channels/' + channelId, { method: 'DELETE' })`
3. `plugin.tsx`: Add `ConfirmModal` component
4. `plugin.tsx`: Add `$showDeleteAgent` + `$deleteAgentHandle` atoms for modal state
5. `plugin.tsx`: In `AgentRow`, add trash button → opens `ConfirmModal`
6. `plugin.tsx`: In `ChannelHeader`, add trash button → opens `ConfirmModal`
7. `plugin.tsx`: On confirm delete agent → call `deleteAgent` → refresh list
8. `plugin.tsx`: On confirm delete channel → call `deleteChannel` → refresh list + close view
9. CSS: `.vector-confirm-modal` styles, red delete button, hover trash icon

test_file: tests/test_pr_017.py
