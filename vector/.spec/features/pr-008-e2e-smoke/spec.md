# PR-008: E2E smoke tests

## Spec

End-to-end regression tests for vector v0 that exercise the full stack
(profiles, channels, mentions, dispatcher, YAML persistence, CLI).

## Acceptance Criteria

- @spec:AC-008-1 — end-to-end dispatch cycle: @mention → dispatcher → agent replies → posted to channel
- @spec:AC-008-2 — YAML round-trip: save_to_yaml → load_from_yaml preserves all profiles
- @spec:AC-008-3 — mention extraction with code-fence exclusion
- @spec:AC-008-4 — FTS5 full-text search returns matching messages
- @spec:AC-008-5 — CLI cross-process persistence (agents add → list in new process)
- @spec:AC-008-6 — no regression on core objects

## test_file

tests/test_pr_008_e2e_smoke.py
