# PR-015: Fix sidebar button icons + UX clarity

## Depends on
PR-014

## Problem
The sidebar header has three buttons, two of which use the same `add` icon. Users can't tell which button creates a channel vs which adds an agent. The "Add Agent" button (robot icon) doesn't open the modal — it just refreshes the agent list. There is a second "add" icon button that actually opens the Add Agent modal. This is confusing.

## Requirements

### REQ-VEC-015-1: Distinct button icons
The sidebar header MUST have exactly two buttons with distinct icons:
- Add Agent: `Codicon name="robot"` (not `add`)
- Create Channel: `Codicon name="comment-discussion"` (not `add`)

### REQ-VEC-015-2: Button tooltips
Each button MUST have a descriptive `title` attribute: "Add Agent" and "Create Channel" respectively.

### REQ-VEC-015-3: Single Add Agent button
Remove the duplicate "refresh agents" button (robot icon). The Add Agent button SHOULD both refresh the agent list AND open the modal. The agent list auto-refreshes on mount and after creation — a manual refresh button is unnecessary.

### REQ-VEC-015-4: Empty sidebar with call-to-action
When both channels and agents lists are empty, the sidebar MUST show two empty-state boxes:
- "No channels. Create one →" (button opens CreateChannelModal)
- "No agents. Add one →" (button opens AddAgentModal)

## Acceptance Criteria

- AC-VEC-015-1: Sidebar header has exactly 2 buttons, one with robot icon (Add Agent), one with comment icon (Create Channel)
- AC-VEC-015-2: No two buttons share the same icon
- AC-VEC-015-3: Clicking "Add Agent" (robot) opens the AddAgentModal
- AC-VEC-015-4: Empty sidebar shows both empty-state CTAs

## Implementation Plan

### Files
- `apps/desktop/src/plugins/vector-channels/plugin.tsx` (~+30 LoC)
- `apps/desktop/src/plugins/vector-channels/vector-channels.css` (~+15 LoC)

### Steps
1. In `SidebarHeader`, remove the `refreshAgents` button (robot icon) — it was confusing
2. Change "Add Agent" button icon from `add` to `robot`
3. Change "Create Channel" button icon from `add` to `comment-discussion`
4. Remove the third button entirely (the duplicate `add` that opened `showAddAgent`)
5. Keep only 2 buttons: robot → `$showAddAgent.set(true)`, comment → `$showCreateChannel.set(true)`
6. In sidebar lower section, when `agents.length === 0`, show "No agents. Add one →" CTA
7. When channels AND agents are both empty, sidebar shows both CTAs stacked

test_file: tests/test_pr_015.py
