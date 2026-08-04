# PR-004 — Agent Runtime (wraps Hermes `delegate_task`)

> **Status:** planned · **Depends on:** PR-001 (AgentProfile) · **Estimated size:** ~200 LoC

## Goal

An `AgentRuntime` that takes an `AgentProfile` plus a message and
returns the agent's response. It does this by wrapping Hermes's own
`delegate_task` mechanism so the agent runs in a fresh, isolated context
with its declared tools and model.

This is the layer that turns a `Profile` into something that actually
responds. No mention parsing happens here — that's PR-002 / PR-005.

## Requirements

- **REQ-VEC-004-1.** `AgentRuntime.run(profile, message, *, timeout=300)`
  MUST return a `RunResult` with `output` (str), `tokens_used` (int),
  `duration_ms` (int), `status` (`ok` | `error` | `timeout`).
- **REQ-VEC-004-2.** `run()` MUST inject the profile's `system_prompt`
  as the agent's first message and prefix the user `message` with the
  agent's `handle` so logs make its identity obvious.
- **REQ-VEC-004-3.** `run()` MUST honor `profile.tools` — the agent
  sees ONLY its declared tools. Other tools are removed.
- **REQ-VEC-004-4.** `run()` MUST use `profile.model`; if absent,
  inherit the calling session's model.
- **REQ-VEC-004-5.** When the timeout elapses, `run()` MUST cancel the
  delegate and return `status="timeout"` with partial output if any.
- **REQ-VEC-004-6.** Errors from the delegate (LLM failure, tool error,
  OOM) MUST be caught and surfaced as `status="error"` with the
  exception class name in `RunResult.error`.
- **REQ-VEC-004-7.** When `profile.fallback_models` is non-empty AND
  the primary attempt fails with a transient error (rate-limit, 5xx,
  network timeout, `status in {"error", "timeout"}`), `run()` MUST
  retry with the next fallback model in order. Only the FIRST
  non-transient error short-circuits (validation/auth errors).
- **REQ-VEC-004-8.** When all fallbacks are exhausted, `run()` MUST
  return `status="error"` with `RunResult.error` containing the chain
  summary (e.g. `"primary=anthropic/claude-sonnet-4.5: rate_limited;
  fallback[0]=openai/gpt-4o: 5xx; fallback[1]=ollama/qwen: oom"`).
- **REQ-VEC-004-9.** When `profile.model` is `None`, the runtime MUST
  inherit the calling session's model and provider (no fallback chain
  in that case — fallbacks only apply when primary is explicit).

## Acceptance criteria

- `AC-VEC-004-1` — `run(gandalf, "hi")` returns a `RunResult` with a
  non-empty `output` and `status="ok"` (uses a fake LLM fixture).
- `AC-VEC-004-2` — The fake LLM receives the system prompt as the
  first message and the user message prefixed with `[gandalf]`.
- `AC-VEC-004-3` — With `profile.tools = ("read_file",)`, the
  delegate call's `tools` argument contains exactly `["read_file"]`.
- `AC-VEC-004-4` — `profile.model = "anthropic/claude-sonnet-4.5"`
  propagates to the delegate call.
- `AC-VEC-004-5` — A delegate that sleeps longer than `timeout=0.1`
  returns `status="timeout"` within 200 ms.
- `AC-VEC-004-6` — A delegate that raises `RuntimeError("boom")`
  returns `status="error"` and `RunResult.error == "RuntimeError"`.
- `AC-VEC-004-7` — With `fallback_models=("gpt-4o",)`, a primary that
  returns `status="error"` with `kind="rate_limited"` triggers the
  fallback; the delegate is invoked again with `model="gpt-4o"` and the
  successful response is returned with `status="ok"`.
- `AC-VEC-004-8` — When primary fails transiently and all fallbacks
  also fail, `RunResult.error` contains the chain summary (one entry
  per attempt in order).
- `AC-VEC-004-9` — A primary that returns `status="error"` with
  `kind="auth_error"` does NOT trigger fallback (non-transient);
  fallbacks only fire for rate-limit/5xx/timeout/oom.

## Files

- `src/vector/runtime.py` — new module (AgentRuntime, RunResult)
- `src/vector/_hermes.py` — thin internal wrapper around
  `hermes_tools.delegate_task` so we can mock it cleanly in tests
- `tests/test_runtime.py` — contract tests using a fake delegate

## Notes

The actual integration with `hermes_tools.delegate_task` lives here but
is wrapped behind an interface, so tests run without depending on the
real Hermes process. The integration smoke test is a separate, manual
step noted in the PR description (not part of CI).

## Hermes references

- `tools/delegate_tool.py:2779` — the real `delegate_task` signature
  this wraps. Calls go in as
  `delegate_task(goal=…, context=…, role="leaf", max_iterations=…)`.
- `apps/desktop/AGENTS.md` — invariants around prompt caching and
  role alternation that `vector` MUST honor.
