# Feature spec — pr-002-mention-parser

This directory exists because `verify-feature.sh pr-002-mention-parser`
expects a `spec.md` here listing every `@spec:AC-VEC-NNN` tag the
contract test must cover. The authoritative AC list lives in the
roadmap spec:

> `docs/roadmap/prs/PR-002-mention-parser.md`

## ACs under contract for PR-002

- `AC-VEC-002-1` — `"hi @gandalf"` → `["gandalf"]`.
- `AC-VEC-002-2` — `"contact user@example.com"` → `[]`.
- `AC-VEC-002-3` — `"@code-review-bot please look"` with known names
  `["code-review-bot"]` → `["code-review-bot"]`.
- `AC-VEC-002-4` — Code fences (``` ``` ```) AND inline backticks
  (`` ` ``) both excluded.
- `AC-VEC-002-5` — `"@a @b @a"` → `["a", "b"]` (no duplicates,
  order preserved).
- `AC-VEC-002-6` — Calling twice with the same input returns equal
  lists (determinism).

## Contract test

test_file: tests/test_pr_002_mention_parser.py

6 AC-mapped tests, each carrying `@pytest.mark.ac_vec_002_N`. 4
extra invariant guards (empty string, only-at-sign, longest-first
matching, MENTION_CAP truncation) — not AC-marked, do not affect
the contract pass/fail summary.

## How to verify

```bash
sh scripts/verify-feature.sh pr-002-mention-parser --json \
  > .spec/verification/pr-002-mention-parser.json
```

The script exits 0 only when every AC above is present in the test
file AND its corresponding test passes.
