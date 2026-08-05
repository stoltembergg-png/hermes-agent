# Feature spec — pr-007-desktop-panel

test_file: tests/test_pr_007_desktop_panel.py

## Acceptance criteria

AC IDs verified by scripts/verify-feature.sh:

- AC-VEC-007-1 — plugin loads, adds Channels nav entry
- AC-VEC-007-2 — new message increments unread badge
- AC-VEC-007-3 — selecting channel shows last 50 messages chronological
- AC-VEC-007-4 — @gandalf hello shows user message + agent reply
- AC-VEC-007-5 — @gan suggests @gandalf (member prefix match)
- AC-VEC-007-6 — no nodeIntegration, context-isolated (static analysis)
