# PR-024: WebSocket live events for real-time updates

## Depends on
PR-011, PR-021

## Problem
The desktop plugin polls for updates. When an agent responds (after LLM dispatch), the new message doesn't appear until the user manually refreshes or re-selects the channel. There is no real-time push from the backend.

## Requirements

### REQ-VEC-024-1: WebSocket events endpoint
Add a WebSocket endpoint `ws://host/api/plugins/vector-channels/events` to `plugin_api.py` that:
- Accepts a connection upgrade
- Subscribes to a channel's event stream
- Pushes events as JSON: `{"type": "message", "channel_id": "...", "message": {...}}`
- Events: `message.new`, `agent.joined`, `agent.left`, `agent.response_start`, `agent.response_complete`

### REQ-VEC-024-2: Event emission in dispatcher
The `Dispatcher.dispatch()` method MUST emit events when:
- A new message is posted to a channel (`message.new`)
- An agent starts processing a mention (`agent.response_start`)
- An agent finishes responding (`agent.response_complete`)

Events are pushed to an `asyncio.Queue` that the WebSocket endpoint drains.

### REQ-VEC-024-3: Frontend WebSocket client
The desktop plugin MUST open a WebSocket connection on `ChannelsPage` mount:
- When a `message.new` event arrives, append the message to the active channel's `$messages`
- When `agent.response_start`, show a typing indicator
- When `agent.response_complete`, hide the typing indicator
- Close WebSocket on unmount

### REQ-VEC-024-4: Typing indicator
When `agent.response_start` fires for the active channel, show a typing indicator in the message list:
- "Agent @<handle> is typing..." with animated dots
- Indicator is hidden when `agent.response_complete` arrives

### REQ-VEC-024-5: Quit polling
The existing polling logic (if any) MUST be removed in favor of WebSocket events. The initial `loadChannelData` still fetches history, but live updates come via WS.

## Acceptance Criteria

- AC-VEC-024-1: When agent responds to a mention, the response message appears in real-time without manual refresh
- AC-VEC-024-2: Typing indicator shows while agent is processing a response
- AC-VEC-024-3: Switching channels still loads history via REST, live messages via WS
- AC-VEC-024-4: WebSocket reconnects on page visibility change (not requiring manual refresh)
- AC-VEC-024-5: Closing the desktop app cleanly destroys the WebSocket connection

## Implementation Plan

### Files
- `plugins/vector-channels/dashboard/plugin_api.py` (~+60 LoC)
- `vector/src/vector/dispatcher.py` (~+30 LoC)
- `vector/src/vector/events.py` (NEW ~50 LoC) — event bus
- `apps/desktop/src/plugins/vector-channels/plugin.tsx` (~+80 LoC)
- `apps/desktop/src/plugins/vector-channels/vector-channels.css` (~+20 LoC)

### Steps
1. Create `vector/src/vector/events.py`:
   - `EventBus` class with `asyncio.Queue` per subscriber
   - `publish(event_type, payload)` → pushes to all subscriber queues
   - `subscribe()` → returns a new queue
2. In `Dispatcher.dispatch()`:
   - Before calling delegate: `bus.publish("agent.response_start", {"handle": handle})`
   - After response: `bus.publish("agent.response_complete", {"handle": handle, "message": msg})`
   - On new message: `bus.publish("message.new", {"channel_id":..., "message": msg})`
3. In `plugin_api.py`:
   - Add `@router.websocket("/events")` handler
   - On connect: `queue = svc.get_event_bus().subscribe()`
   - Loop: `event = await queue.get()` → `await ws.send_json(event)`
   - On disconnect: unsubscribe
4. In `plugin.tsx`:
   - On `ChannelsPage` mount, open WebSocket to `events` endpoint
   - Handle `message.new`: if `channel_id === activeChannel`, append to `$messages`
   - Handle `agent.response_start`: set `$typingAgent` atom
   - Handle `agent.response_complete`: clear `$typingAgent`, append message
5. Render typing indicator in message list when `$typingAgent` is set
6. CSS: typing indicator animation (three bouncing dots)

test_file: tests/test_pr_024.py
