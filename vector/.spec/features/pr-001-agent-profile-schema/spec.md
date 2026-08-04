# Feature spec — pr-001-agent-profile-schema

This directory exists because `verify-feature.sh pr-001-agent-profile-schema`
expects a `spec.md` here listing every `@spec:AC-VEC-NNN` tag the
contract test must cover. The authoritative AC list lives in the
roadmap spec:

> `docs/roadmap/prs/PR-001-agent-profile-schema.md`

## ACs under contract for PR-001

- `AC-VEC-001-1` — YAML round-trip equals input.
- `AC-VEC-001-2` — JSON round-trip equals input.
- `AC-VEC-001-3` — Invalid handle raises `InvalidHandleError` with
  the offending value in the message.
- `AC-VEC-001-4` — `AgentRegistry.register` raises `DuplicateHandleError`
  on duplicate.
- `AC-VEC-001-5` — Constructing with an unknown model raises
  `UnknownModelError`.
- `AC-VEC-001-6` — `fallback_models` containing the primary model
  raises `InvalidFallbackChainError`; empty list is valid.
- `AC-VEC-001-7` — `model=None` and `provider=None` are valid (inherit).

## Contract test

test_file: tests/test_pr_001_agent_profile_schema.py

7 AC-mapped tests, each carrying `@pytest.mark.ac_vec_001_N`. 2
extra invariant guards (not AC-marked, do not affect the contract
pass/fail summary).

## How to verify

```bash
sh scripts/verify-feature.sh pr-001-agent-profile-schema --json \
  > .spec/verification/pr-001-agent-profile-schema.json
```

The script exits 0 only when every AC above is present in the test
file AND its corresponding test passes.
