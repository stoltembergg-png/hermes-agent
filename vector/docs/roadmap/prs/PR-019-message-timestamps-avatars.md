# PR-019: Message timestamps + author avatars

## Depends on
PR-011

## Problem
Message rows show `@handle` text followed by the message body. There are no visual avatars, messages from agents and humans look the same, and timestamps are plain text without relative formatting. The message list is hard to scan visually.

## Requirements

### REQ-VEC-019-1: Author avatars
Each message row MUST show an avatar before the author handle:
- Human (`human`): Codicon `account` with human-blue background
- Agents: Codicon `robot` with accent-color background
Avatar is a 28px circle with the icon centered.

### REQ-VEC-019-2: Relative timestamps
Message timestamps MUST be formatted as relative time:
- < 60s: "just now"
- < 60m: "Xm ago"
- < 24h: "Xh ago"
- >= 24h: full date `Mon DD, HH:MM`

### REQ-VEC-019-3: Message grouping
Consecutive messages from the same author within 5 minutes MUST be grouped:
- First message shows avatar + handle + timestamp
- Subsequent messages show indented body only (no avatar, no handle)
- New author or >5min gap resets the group

### REQ-VEC-019-4: Markdown rendering
Message body SHOULD render basic markdown: `**bold**`, `*italic*`, `` `code` ``, and line breaks. Use a lightweight renderer (not full react-markdown) — just regex-based inline formatting.

## Acceptance Criteria

- AC-VEC-019-1: Messages show circular avatars (human=account icon, agent=robot icon)
- AC-VEC-019-2: Timestamps show "just now", "5m ago", "2h ago", or full date for older
- AC-VEC-019-3: Consecutive messages from same author within 5min are grouped (no repeated avatar/handle)
- AC-VEC-019-4: Bold/italic/code markdown in message body renders as styled HTML

## Implementation Plan

### Files
- `apps/desktop/src/plugins/vector-channels/plugin.tsx` (~+100 LoC)
- `apps/desktop/src/plugins/vector-channels/vector-channels.css` (~+40 LoC)

### Steps
1. Add `relativeTime(dateString: string): string` helper
2. Add `formatMarkdown(text: string): string` helper — returns HTML string with `<strong>`, `<em>`, `<code>`
3. Update `MessageRow` to show avatar (28px circle with Codicon)
4. In `MessageRow`, check if previous message has same author + within 5min → grouped mode (no avatar/handle)
5. Use `dangerouslySetInnerHTML` for formatted message body
6. CSS: avatar circle, message grouping indent, markdown styles

test_file: tests/test_pr_019.py
