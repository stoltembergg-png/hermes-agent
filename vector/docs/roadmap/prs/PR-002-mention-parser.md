# PR-002 — `@mention` Parser

> **Status:** planned · **Depends on:** none (consumed by PR-005) · **Estimated size:** ~120 LoC

## Goal

A pure-Python parser that extracts `@<handle>` mentions from a chat
message. Handles word boundaries, multi-word display names (longest-first
match against a known set), and code-fence exclusion so that
`` `@gandalf` `` inside triple backticks is not matched.

Adapted from `stoltembergg-png/buzz`'s `crates/buzz-sdk/src/mentions.rs`,
but stripped of Nostr specifics and made Pythonic.

## Requirements

- **REQ-VEC-002-1.** `extract_mentions(text)` MUST return a deduplicated,
  ordered list of lowercased handles.
- **REQ-VEC-002-2.** A `@handle` MUST be preceded by whitespace or
  start-of-string. `user@host` MUST NOT match.
- **REQ-VEC-002-3.** When `known_names` is supplied, multi-word names
  MUST be tried longest-first.
- **REQ-VEC-002-4.** Text inside fenced code blocks (``` ``` ```) and
  inline code spans (`` ` ``) MUST be excluded.
- **REQ-VEC-002-5.** The function MUST be pure (no I/O, no globals) and
  return value MUST be deterministic for the same input.

## Acceptance criteria

- `AC-VEC-002-1` — `"hi @gandalf"` → `["gandalf"]`.
- `AC-VEC-002-2` — `"contact user@example.com"` → `[]`.
- `AC-VEC-002-3` — `"@code-review-bot please look"` with known names
  `["code-review-bot"]` → `["code-review-bot"]`.
- `AC-VEC-002-4` — `"see ```@gandalf``` and `@frodo`"` → `["frodo"]`
  (gandalf is in fenced code, frodo in inline — inline is also excluded).
- `AC-VEC-002-5` — `"@a @b @a"` → `["a", "b"]` (order preserved, no dup).
- `AC-VEC-002-6` — Calling twice with the same input returns equal lists.

## Files

- `src/vector/mention.py` — new module
- `tests/test_mention.py` — contract tests, one per AC

## Reference

`stoltembergg-png/buzz/crates/buzz-sdk/src/mentions.rs` — same algorithm,
Nostr-agnostic. We borrow the `MENTION_CAP = 50` constant.
