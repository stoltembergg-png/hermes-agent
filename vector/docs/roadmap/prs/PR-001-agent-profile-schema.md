# PR-001 — Agent Profile Schema

> **Status:** planned · **Depends on:** none · **Estimated size:** ~150 LoC

## Goal

Define the canonical `AgentProfile` data model: a named handle, a system
prompt, an explicit toolset, a default model, and a serialization format
that round-trips through YAML and JSON without loss.

This is the foundation. Every other PR consumes `AgentProfile`.

## Requirements

- **REQ-VEC-001-1.** The profile MUST be a frozen dataclass with the
  fields: `handle` (str, slug), `system_prompt` (str), `tools`
  (tuple[str, ...]), `model` (str | None), `provider` (str | None),
  `fallback_models` (tuple[str, ...]), `description` (str),
  `created_at` (datetime), `updated_at` (datetime).
- **REQ-VEC-001-2.** The handle MUST be lowercase, `[a-z0-9._-]{2,32}`,
  and unique per registry.
- **REQ-VEC-001-3.** The profile MUST serialize to YAML and JSON with
  no information loss.
- **REQ-VEC-001-4.** The profile MUST round-trip: `load(yaml(dump(p)))`
  equals `p` for any valid `p`.
- **REQ-VEC-001-5.** `model` and `provider` MUST be `None` (inherit) OR
  a value present in the **current Hermes provider/model catalog**
  (queried via `hermes model list` or equivalent). Construction with an
  unknown value raises `UnknownModelError`.
- **REQ-VEC-001-6.** `fallback_models` MUST NOT contain duplicates and
  MUST NOT contain the primary `model`. Each entry MUST be valid per
  REQ-VEC-001-5.

## Acceptance criteria

- `AC-VEC-001-1` — Given a valid `AgentProfile`, `dump_yaml(p)` produces
  a string that `load_yaml(s)` parses back to an equal profile.
- `AC-VEC-001-2` — Given a valid `AgentProfile`, `dump_json(p)` produces
  a string that `load_json(s)` parses back to an equal profile.
- `AC-VEC-001-3` — Constructing with an invalid handle raises
  `InvalidHandleError`; the message includes the offending value.
- `AC-VEC-001-4` — `AgentRegistry.register(p)` raises
  `DuplicateHandleError` if a profile with the same handle already
  exists.
- `AC-VEC-001-5` — Constructing with `model="gpt-9000/imaginary"` when
  Hermes' catalog does not list it raises `UnknownModelError` and the
  profile is NOT registered.
- `AC-VEC-001-6` — Constructing with `fallback_models` containing the
  primary `model` raises `InvalidFallbackChainError`; an empty list is
  valid (means "no fallback").
- `AC-VEC-001-7` — `model=None` and `provider=None` are valid and mean
  "inherit from channel / session".

## Files

- `src/vector/profile.py` — new module
- `tests/test_profile.py` — contract tests, one per AC

## Out of scope

- Persistence (lives in PR-003 / channel store).
- Tool validation against the Hermes toolset (lives in PR-004).
