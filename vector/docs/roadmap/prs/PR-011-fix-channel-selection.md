# PR-011: Fix channel selection + message display

## Depends on
PR-010 (merged as `249df18fe`)

## Problem
When user clicks a channel in the sidebar, the message area does not visibly change. The `loadChannelData` function fetches history and members, but:
1. No channel name/member header is shown in the message area
2. When a channel has 0 messages, the view shows nothing (no empty state)
3. New messages from `postAndDispatch` replace the entire list instead of appending
4. No auto-scroll to bottom on new messages

## Requirements

### REQ-VEC-011-1: Channel header
When a channel is selected, the message area MUST display a header showing:
- Channel name (bold)
- Member list as `@handle` chips
- Member count badge

### REQ-VEC-011-2: Empty message state
When a channel is selected but has 0 messages, the message area MUST show:
- "No messages yet" placeholder
- Hint: "Start chatting below — use @handle to mention agents"

### REQ-VEC-011-3: Message append (not replace)
`postAndDispatch` MUST append new messages to the existing `$messages` atom, not replace the entire array. The backend response includes all messages; the UI should merge deduplicating by message ID.

### REQ-VEC-011-4: Auto-scroll
After new messages are added, the message list MUST auto-scroll to the bottom. Use a `ref` on the message list container and `scrollIntoView` on the last message.

## Acceptance Criteria

- AC-VEC-011-1: When user clicks channel "dev-team" in sidebar, message area shows header "dev-team" with member chips @human @gandalf
- AC-VEC-011-2: When selected channel has 0 messages, message area shows "No messages yet" placeholder with hint text
- AC-VEC-011-3: After posting a message, the message appears appended to the list (not replacing previous messages)
- AC-VEC-011-4: After posting, the message list scrolls to show the newest message at the bottom

## Implementation Plan

### Files
- `apps/desktop/src/plugins/vector-channels/plugin.tsx` (~+80 LoC)

### Steps
1. Add `$channelName` atom — set when channel is selected (lookup from `$channels`)
2. Add `ChannelHeader` component — shows channel name + member chips
3. In `ChannelsPage`, render `<ChannelHeader />` above message list when `activeChannel` is set
4. In message area, when `messages.length === 0 && activeChannel`, show empty state div
5. Fix `postAndDispatch` — merge result.messages with existing $messages, dedup by `msg.id`
6. Add `useRef` + `useEffect` on message list — scroll to bottom when `messages.length` changes
7. In `ChannelRow`, also fetch channel name for header (already available in ChannelInfo)

### Test
- Vitest: `plugin.test.ts` — verify `postAndDispatch` merges messages by ID, not replaces
