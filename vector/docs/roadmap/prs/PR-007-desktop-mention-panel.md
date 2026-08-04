# PR-007 — Desktop Mention Panel (Hermes Desktop Plugin)

> **Status:** planned · **Depends on:** PR-005, PR-006 · **Estimated size:** ~250 LoC

## Goal

A Hermes Desktop plugin that adds a **Channels** side panel listing all
`vector` channels, the recent messages, and a composer that posts via
the dispatcher. This is the first surface where humans and agents
converse side-by-side in real time.

## Requirements

- **REQ-VEC-007-1.** The plugin MUST register a `vector-channels` panel
  via the existing Hermes desktop plugin API.
- **REQ-VEC-007-2.** The panel MUST show the channel list, with a
  badge for unread messages since the last view.
- **REQ-VEC-007-3.** Selecting a channel MUST show its history
  (last 50 messages) with author handle, timestamp, and body.
- **REQ-VEC-007-4.** The composer MUST accept text, post it on Enter,
  and render the dispatcher responses inline as they arrive.
- **REQ-VEC-007-5.** `@<handle>` in the composer MUST auto-complete
  against the members of the active channel.
- **REQ-VEC-007-6.** The plugin MUST ship its own JS bundle (no
  CDN-loaded code) and follow Hermes' desktop plugin security model
  (no `nodeIntegration`, context-isolated).

## Acceptance criteria

- `AC-VEC-007-1` — Plugin loads in Hermes Desktop without console
  errors and adds a "Channels" entry to the sidebar.
- `AC-VEC-007-2` — A new message in a channel increments the unread
  badge; opening the panel clears it.
- `AC-VEC-007-3` — Selecting `dev-room` shows the last 50 messages in
  chronological order.
- `AC-VEC-007-4` — Typing `@gandalf hello` and pressing Enter shows
  the user message and the agent's reply in the message list.
- `AC-VEC-007-5` — Typing `@gan` suggests `@gandalf` if `gandalf` is
  a member of the active channel.
- `AC-VEC-007-6` — DevTools confirms `nodeIntegration === false` and
  the preload exposes only the documented `vector.*` API.

## Files

- `desktop/vector-channels/` — new Hermes desktop plugin
  - `plugin.js` — entry, panel registration
  - `panel.html` — markup
  - `panel.css` — styles (uses Hermes' CSS variables only)
  - `panel.js` — UI logic, IPC to backend
- `desktop/vector-channels/preload.js` — context-isolated bridge
- `tests/test_plugin.py` — Playwright/CheerpJ smoke test
  (manual for v0; automated in v1)

## Hermes references

The plugin lives at
[`apps/desktop/src/plugins/`](https://github.com/stoltembergg-png/hermes-agent/tree/43717123c/apps/desktop/src/plugins)
and is loaded by the runtime in
[`apps/desktop/src/contrib/runtime-loader.ts`](https://github.com/stoltembergg-png/hermes-agent/blob/43717123c/apps/desktop/src/contrib/runtime-loader.ts).
The mandatory shape of a plugin is documented in
[`apps/desktop/src/plugins/README.md`](https://github.com/stoltembergg-png/hermes-agent/blob/43717123c/apps/desktop/src/plugins/README.md).
Three plugins serve as live templates we MUST mirror:

- `plugins/example/` — minimal "hello world" panel (manifest + render)
- `plugins/gateway-pill/` — sidebar pill that subscribes to gateway
  state — close to what `vector`'s channel badge needs
- `plugins/kanban/` — full sidebar panel with reactive list — closest
  template to a multi-channel browser

## Notes

This PR exists to validate that the backend from PR-001..005 is usable
from a real Hermes surface. The plugin is intentionally small — the
real visual polish lands in a follow-up.
