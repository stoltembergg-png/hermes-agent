# PR-018: Channel member list in channel view

## Depends on
PR-011

## Problem
When viewing a channel, there is no visible list of who is in the channel. The members are only shown in the "Create Channel" modal (as toggle chips). Users have no way to see who can receive messages in a channel.

## Requirements

### REQ-VEC-018-1: Member list panel
The channel header (from PR-011) MUST show a collapsible member list with avatars. Each member row shows:
- Avatar/Codicon (robot for agents, account for human)
- `@handle`
- Role label: "Agent" or "You"

### REQ-VEC-018-2: Member count badge
The channel header MUST show a member count badge next to the channel name: `#dev-team (3 members)`.

### REQ-VEC-018-3: Add member to channel
Below the member list, a "Add member" button opens a dropdown of registered agents NOT currently in the channel. Selecting one adds them to the channel.

### REQ-VEC-018-4: Leave channel
The human member can see a "Leave channel" button in the member list. This removes 'human' from the channel.

## Acceptance Criteria

- AC-VEC-018-1: Channel header shows all members with @handle and role
- AC-VEC-018-2: Member count is shown as `(N members)` in the header
- AC-VEC-018-3: "Add member" button shows a list of agents not in the channel
- AC-VEC-018-4: Selecting an agent from the dropdown adds them to the channel
- AC-VEC-018-5: "Leave channel" removes 'human' from the channel

## Implementation Plan

### Files
- `apps/desktop/src/plugins/vector-channels/plugin.tsx` (~+80 LoC)
- `apps/desktop/src/plugins/vector-channels/api.ts` (~+15 LoC)
- `apps/desktop/src/plugins/vector-channels/vector-channels.css` (~+25 LoC)
- `plugins/vector-channels/dashboard/plugin_api.py` (~+20 LoC)

### Steps
1. `plugin_api.py`: Add `POST /channels/{id}/members` endpoint — takes `{"handle": "..."}`, calls `svc.create_channel` logic for add_member
2. `plugin_api.py`: Add `DELETE /channels/{id}/members/{handle}` endpoint — removes a member
3. `api.ts`: Add `addMember(channelId, handle)` and `removeMember(channelId, handle)`
4. `plugin.tsx`: Expand `ChannelHeader` to show member list (collapsible via `<details>`)
5. `plugin.tsx`: Add "Add member" dropdown — shows agents in `$agentDetails` not in `$members` for current channel
6. `plugin.tsx`: On add member, call `addMember` and refresh `$members`
7. `plugin.tsx`: Add "Leave channel" button for human
8. CSS: member list panel, avatar styles, add-member dropdown

test_file: tests/test_pr_018.py
