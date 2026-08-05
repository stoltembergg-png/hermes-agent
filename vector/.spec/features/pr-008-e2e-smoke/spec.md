# Feature spec — pr-008-e2e-smoke

test_file: tests/test_pr_008_e2e_smoke.py

## Acceptance criteria

AC IDs verified by scripts/verify-feature.sh:

- AC-VEC-008-1 — end-to-end dispatch cycle: @mention → dispatcher → agent replies → posted to channel
- AC-VEC-008-2 — YAML round-trip: save_to_yaml → load_from_yaml preserves all profiles
- AC-VEC-008-3 — mention extraction with code-fence exclusion
- AC-VEC-008-4 — FTS5 full-text search returns matching messages
- AC-VEC-008-5 — CLI cross-process persistence (agents add → list in new process)
- AC-VEC-008-6 — no regression on core objects
