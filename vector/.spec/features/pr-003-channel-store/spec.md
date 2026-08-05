# Feature spec — pr-003-channel-store

test_file: tests/test_pr_003_channel_store.py

## Acceptance criteria

AC IDs verified by scripts/verify-feature.sh:

- AC-VEC-003-1 — create round-trip
- AC-VEC-003-2 — duplicate membership raises
- AC-VEC-003-3 — unregistered handle raises
- AC-VEC-003-4 — post extracts mentions
- AC-VEC-003-5 — history chronological
- AC-VEC-003-6 — FTS5 search
- AC-VEC-003-7 — soft/hard member limits
- AC-VEC-003-8 — DM cap of exactly 2
