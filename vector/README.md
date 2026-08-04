# vector

> **Note:** `vector` was originally a separate repository (`stoltembergg-png/vector`) and was consolidated into the
> `hermes-agent` monorepo on 2026-08-04 so integration tests against the real Hermes
> modules are trivial to write. The original repo is archived (empty placeholder).

Multi-agent orchestration layer for **Hermes Agent**.

`vector` adds four things on top of Hermes:

1. **Named agent profiles** — register an agent with a handle, system
   prompt, toolset, and default model. Reusable across sessions.
2. **`@mention` dispatch** — type `@gandalf` in any chat and Hermes
   routes the message to that agent's run-loop and streams its reply
   back into the conversation.
3. **Group channels** — persistent multi-member spaces where humans and
   agents post side-by-side, with a shared message log.
4. **Inter-agent conversation** — agents in a channel can `@mention`
   each other; the channel dispatches the message and the named agent
   responds, all inside the same channel.

## Status

v0 — design + first two PRs landing. Implementation in small,
spec-driven PRs (see `docs/roadmap/prs/`).

## Inspiration

Patterned after `stoltembergg-png/buzz`'s channels, mentions, and
`handoff.rs`, but adapted to Hermes Agent's architecture (Python,
`delegate_task`, gateway, profiles, skills, `config.yaml`).

## Install

```bash
pip install -e .
```

## Quick start

```bash
# register an agent
vector agents add gandalf --system "You are a code review wizard." \
  --model anthropic/claude-sonnet-4.5 --tools "read_file,search_files,patch"

# open a channel
vector channels add dev-room --members gandalf,reviewer,you

# talk to an agent
vector chat --channel dev-room
> @gandalf please review the diff in src/agent.py
```

## Roadmap

See `docs/roadmap/prs/`. Each `PR-NNN-<slug>.md` is a single shippable
unit with `REQ-VEC-NNN` requirements and `AC-VEC-NNN` acceptance
criteria.

| PR    | Title                          | Status   |
|-------|--------------------------------|----------|
| 001   | Agent profile schema           | planned  |
| 002   | `@mention` parser              | planned  |
| 003   | Channel store (SQLite)         | planned  |
| 004   | Agent runtime (wraps Hermes)   | planned  |
| 005   | Channel dispatcher             | planned  |
| 006   | `vector` CLI                   | planned  |
| 007   | Desktop mention panel plugin   | planned  |

## License

MIT.
