# Feature spec — pr-005-channel-dispatcher

test_file: tests/test_pr_005_dispatcher.py

## Acceptance criteria

AC IDs verified by scripts/verify-feature.sh:

- AC-VEC-005-1 — @gandalf hi → one response by gandalf
- AC-VEC-005-2 — @stranger (non-member) → zero responses
- AC-VEC-005-3 — self-mention ignored
- AC-VEC-005-4 — cycle stops at depth 3, raises RecursionLimitExceeded
- AC-VEC-005-5 — history contains original + response in order
- AC-VEC-005-6 — sequential: a runs first, b sees a's response
