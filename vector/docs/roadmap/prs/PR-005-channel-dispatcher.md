# PR-005 — Channel Dispatcher

> **Status:** planned · **Depends on:** PR-002, PR-003, PR-004 · **Estimated size:** ~180 LoC

## Goal

The dispatcher is what makes inter-agent conversation real. Given a
new message in a channel:

1. Extract `@mentions` via the parser from PR-002.
2. For each mentioned agent (in order of appearance), run the
   `AgentRuntime` from PR-004 with the message + channel context.
3. Append the agent's response as a new message authored by that
   agent's handle.
4. If the agent's response itself contains `@mentions`, recurse
   (depth-limited to avoid cycles).

This is the heart of `vector` — the part that makes a group chat of
agents actually feel like a conversation.

## Requirements

- **REQ-VEC-005-1.** `Dispatcher.dispatch(channel, message)` MUST
  process the message synchronously and return a `DispatchResult`
  listing every response posted.
- **REQ-VEC-005-2.** The dispatcher MUST only invoke agents that are
  members of the channel. `@stranger` in `#dev-room` is silently
  ignored.
- **REQ-VEC-005-3.** Agents MUST NOT reply to themselves (`@gandalf`
  posted by gandalf is ignored).
- **REQ-VEC-005-4.** Recursion depth MUST be capped at `MAX_DEPTH = 3`
  to prevent infinite agent loops. A `RecursionLimitExceeded`
  exception is raised past the cap.
- **REQ-VEC-005-5.** Each agent response MUST be persisted via
  `ChannelStore.post()` with `author_handle` set to the agent's
  handle — visible in channel history.
- **REQ-VEC-005-6.** The dispatcher MUST run agents **sequentially**
  (not parallel) so that an agent can see earlier agent replies in
  the same dispatch cycle.

## Acceptance criteria

- `AC-VEC-005-1` — Posting `@gandalf hi` to a channel containing
  `gandalf` results in one response message authored by `gandalf`.
- `AC-VEC-005-2` — Posting `@stranger hi` to a channel where
  `stranger` is NOT a member results in zero response messages.
- `AC-VEC-005-3` — When `gandalf` posts `@gandalf self`, no new
  message is produced (self-mention ignored).
- `AC-VEC-005-4` — A cycle `a → b → a → b → a` stops at depth 3 and
  raises `RecursionLimitExceeded`.
- `AC-VEC-005-5` — After dispatch, `ChannelStore.history(channel)`
  contains the original message AND the agent's response, in order.
- `AC-VEC-005-6` — When `@a @b` is posted, `a` runs first and its
  response is visible to `b` via `ChannelStore.history` before `b`
  runs.

## Files

- `src/vector/dispatcher.py` — new module (Dispatcher, DispatchResult)
- `tests/test_dispatcher.py` — contract tests using fake runtime +
  temp SQLite

## Out of scope

- Parallel agent execution (future work; needs careful ordering).
- Streaming responses into the channel as the agent generates them
  (desktop plugin PR will handle live updates).
