# PR-006 — `vector` CLI

> **Status:** planned · **Depends on:** PR-001, PR-002, PR-003, PR-004, PR-005 · **Estimated size:** ~220 LoC

## Goal

A user-facing CLI (`vector agents …`, `vector channels …`, `vector chat …`)
that ties everything together. Uses Python's stdlib `argparse` and
`asyncio` — no third-party CLI framework.

## Requirements

- **REQ-VEC-006-1.** `vector agents add <handle> --system "..." --tools
  "a,b,c" --model "..." --provider "..." --fallback-models "m1,m2"`
  MUST register a new profile. `--model` and `--provider` MUST be
  validated against Hermes' live provider/model catalog
  (`hermes model list`); unknown values abort with `UnknownModelError`.
- **REQ-VEC-006-2.** `vector agents list` MUST print a table of all
  registered profiles.
- **REQ-VEC-006-3.** `vector channels add <name> --members "a,b,c"`
  MUST create a channel and add members. If the resulting member count
  reaches the soft cap (50), emit a warning; if it would exceed the
  hard cap (200), abort with `ChannelTooLargeError`.
- **REQ-VEC-006-4.** `vector channels list` MUST print all channels
  with member counts.
- **REQ-VEC-006-5.** `vector chat --channel <name>` MUST start an
  interactive REPL: prompts with `>`, posts the message via the
  dispatcher, prints agent responses with their handle prefix
  (`@gandalf > …`), and exits on `/quit`.
- **REQ-VEC-006-6.** `vector --version` MUST print the version from
  `pyproject.toml`.
- **REQ-VEC-006-7.** `vector channels add-member <name> <handle>` MUST
  add a single member (1-a-1 case), enforcing the same soft/hard caps
  as REQ-VEC-006-3.
- **REQ-VEC-006-8.** `vector channels add-team <name> --handles
  "a,b,c,..."` MUST add a list of members atomically: either all are
  added or none (rollback on cap violation or duplicate).

## Acceptance criteria

- `AC-VEC-006-1` — `vector agents add gandalf --system "x"` succeeds
  and the profile is loadable on a fresh process invocation.
- `AC-VEC-006-2` — `vector agents list` after adding two profiles
  prints both handles.
- `AC-VEC-006-3` — `vector channels add dev-room --members
  gandalf,reviewer,you` creates the channel and lists both members.
- `AC-VEC-006-4` — `vector channels list` shows `dev-room` with
  member count 3.
- `AC-VEC-006-5` — A scripted REPL session: post `@gandalf hi`, the
  CLI prints `@gandalf > <response>`, then `/quit` exits 0.
- `AC-VEC-006-6` — `vector --version` prints `vector 0.1.0`.
- `AC-VEC-006-7` — Adding a single member to a channel with 200
  members raises `ChannelTooLargeError` and exits non-zero.
- `AC-VEC-006-8` — `add-team` with 5 members succeeds atomically;
  adding a 6th that would exceed the hard cap rolls back all 5 and
  exits non-zero.

## Files

- `src/vector/cli.py` — new module (argparse + asyncio REPL)
- `pyproject.toml` — `[project.scripts]` entry `vector =
  "vector.cli:main"`
- `tests/test_cli.py` — uses subprocess + a fake dispatcher to assert
  the REPL works end-to-end

## Notes

The CLI REPL is intentionally minimal — no readline magic, no colors.
The desktop plugin (PR-007) is where the rich UX lives.
