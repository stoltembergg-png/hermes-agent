# Feature spec — pr-006-cli

test_file: tests/test_pr_006_cli.py

## Acceptance criteria

AC IDs verified by scripts/verify-feature.sh:

- AC-VEC-006-1 — agents add persists across process
- AC-VEC-006-2 — agents list prints both handles
- AC-VEC-006-3 — channels add creates channel with members
- AC-VEC-006-4 — channels list shows member count
- AC-VEC-006-5 — scripted REPL: post, response, /quit
- AC-VEC-006-6 — vector --version prints 0.1.0
- AC-VEC-006-7 — hard cap (200) raises ChannelTooLargeError
- AC-VEC-006-8 — add-team atomic: 5 succeed, 6th exceeds cap → rollback
