# Feature spec — pr-004-agent-runtime

test_file: tests/test_pr_004_agent_runtime.py

## Acceptance criteria

AC IDs verified by scripts/verify-feature.sh:

- AC-VEC-004-1 — run returns RunResult with non-empty output, status=ok
- AC-VEC-004-2 — system prompt as first message, user message prefixed with [handle]
- AC-VEC-004-3 — profile.tools propagate to delegate call
- AC-VEC-004-4 — profile.model propagates to delegate call
- AC-VEC-004-5 — timeout returns status=timeout within 200ms
- AC-VEC-004-6 — delegate raises → status=error, error=exception class name
- AC-VEC-004-7 — fallback triggered by transient error (rate_limited)
- AC-VEC-004-8 — all fallbacks fail → chain summary in error
- AC-VEC-004-9 — non-transient error (auth_error) does NOT trigger fallback
