# AGENTS.md — `vector`

> Agent-orchestration layer for **Hermes Agent**: named agent profiles,
> `@mention` dispatch, group channels, and inter-agent conversation.

This project takes the patterns we use in `stoltembergg-png/buzz` (Nostr-style
channels, mentions with p-tags, agent handoffs) and adapts them for **Hermes
Agent**'s architecture (`delegate_task`, gateway, profiles, skills,
`config.yaml`).

## Goals

1. **Named agent profiles.** A user can register an agent with a stable
   handle (`@gandalf`, `@reviewer`, `@sre`), a system prompt, toolset, and
   default model — and reference it from any session.
2. **`@mention` dispatch.** Inside any chat session (CLI, TUI, desktop,
   gateway platform), typing `@<agent>` routes the message to that agent's
   run-loop and returns its response inline.
3. **Group channels.** A persistent, multi-member space where many agents
   (and humans) can post, read history, and be `@mentioned` together.
4. **Inter-agent conversation.** Agents in a channel can address each
   other with `@<agent>` and the channel dispatches the message back to
   the named agent, which produces a response that re-enters the channel
   as that agent's voice.

## Non-goals (v0)

- Cross-host mesh / Nostr relays — we use local state first, defer the
  relay to v1.
- Cross-LLM handoffs that mutate the parent context — Hermes already has
  `delegate_task`; we wrap, not replace.
- Mobile / desktop UI redesign — the desktop app picks up new panels via
  its existing plugin API; we ship the backend.

## Workflow (per PR)

We follow the **`spec-driven-pr-implementation`** skill exactly:

```
read spec → feature branch → contract test @spec:AC-NNN → verify-feature.sh
→ push → 3 checks verde → merge --admin --squash --delete-branch
→ .spec/verification/<feature>.json
→ close draft PR original com comentário apontando para a PR real
```

Specs live in `docs/roadmap/prs/PR-NNN-<slug>.md`. Every requirement ID is
`REQ-VEC-NNN`. Every acceptance criterion is `AC-VEC-NNN`. Tests must carry
the corresponding `@spec:AC-VEC-NNN` tag.

## Hermes Contracts (authoritative references)

Every `vector` PR MUST cite the **real** Hermes Agent code that it wraps,
adapts, or extends. The authoritative reference copy is at
[`stoltembergg-png/hermes-agent`](https://github.com/stoltembergg-png/hermes-agent),
which mirrors
[`NousResearch/hermes-agent`](https://github.com/NousResearch/hermes-agent)
on commit `43717123c` (the `main` HEAD at the time of `vector` bootstrap).

### PR-004 — wrapping `delegate_task`

The `AgentRuntime` adapts the real delegate tool defined in
[`tools/delegate_tool.py:2779`](https://github.com/stoltembergg-png/hermes-agent/blob/43717123c/tools/delegate_tool.py#L2779):

```python
def delegate_task(
    goal: Optional[str] = None,
    context: Optional[str] = None,
    tasks: Optional[List[Dict[str, Any]]] = None,
    max_iterations: Optional[int] = None,
    role: Optional[str] = None,            # 'leaf' | 'orchestrator'
    background: Optional[bool] = None,
    parent_agent=None,
) -> str:
```

`vector` calls `delegate_task(goal=…, context=…, role="leaf")` per agent
response. The `role="leaf"` constraint (REQ-VEC-005-4 recursion cap)
aligns with the upstream invariant: a delegated agent cannot further
delegate, so `vector`'s own recursion cap is the only enforcement layer
needed at the orchestrator level.

### PR-004 — provider/model catalog

`vector` validates `AgentProfile.model` / `provider` against the live
Hermes catalog. The model catalog is **dynamically fetched** (see
`fix(models): a model id missing its vendor prefix says so instead of
404ing` — commit `43717123c`); `vector` MUST query it on every
`agents add` rather than hardcode any model name.

### PR-007 — desktop plugin API

The Hermes Desktop plugin API lives in
[`apps/desktop/src/contrib/`](https://github.com/stoltembergg-png/hermes-agent/tree/43717123c/apps/desktop/src/contrib):
- `plugin.ts`, `registry.ts`, `runtime-loader.ts` — runtime + manifest
- `plugins/example/` — minimal working plugin (template)
- `plugins/gateway-pill/`, `plugins/kanban/` — production reference
  plugins for sidebar panels
- `plugins/README.md` — plugin authoring guide

The renderer-side SDK (`apps/desktop/src/sdk/`) exposes `runtime.ts` as
the only stable import surface. Backend calls go through the existing
Electron capability bridge (no direct Node access from plugins).

### Upstream invariants `vector` MUST honor

From [`apps/desktop/AGENTS.md`](https://github.com/stoltembergg-png/hermes-agent/blob/43717123c/apps/desktop/AGENTS.md)
and [`AGENTS.md`](https://github.com/stoltembergg-png/hermes-agent/blob/43717123c/AGENTS.md):

- **Plugins live in their own directory** and work within the
  `contrib/` ABCs. No core-file edits from `vector`. PR-007 ships a
  standalone plugin registered at install time.
- **No `nodeIntegration`, context-isolated** in any renderer code.
- **Secrets in `.env`, settings in `config.yaml`** — `vector` config
  goes to `~/.hermes/config.yaml` under `vector:` namespace.
- **Preserve prompt caching** — `vector` MUST NOT mutate past context;
  each agent runs in a fresh `delegate_task` invocation.
- **Strict message role alternation** — `vector` dispatcher MUST NOT
  inject synthetic user messages into an agent's running conversation.

## Layout (inside `hermes-agent`)

```
hermes-agent/
├── vector/                          ← THIS project (was a separate repo)
│   ├── AGENTS.md
│   ├── README.md
│   ├── docs/roadmap/prs/
│   │   ├── PR-001-agent-profile-schema.md
│   │   ├── PR-002-mention-parser.md
│   │   ├── PR-003-channel-store.md
│   │   ├── PR-004-agent-runtime.md
│   │   ├── PR-005-channel-dispatcher.md
│   │   ├── PR-006-cli-agents.md
│   │   └── PR-007-desktop-mention-panel.md
│   ├── src/vector/                  # AgentProfile, mention, channel,
│   │   ├── profile.py               # runtime, dispatcher, CLI
│   │   ├── mention.py
│   │   ├── channel.py
│   │   ├── runtime.py
│   │   ├── dispatcher.py
│   │   └── cli.py
│   ├── tests/                       # contract tests + AC markers
│   ├── scripts/verify-feature.sh
│   └── .spec/                       # features/ + verification/ JSON
├── agent/                           ← core Hermes modules vector
├── tools/delegate_tool.py           ← integrates with
├── pyproject.toml                   ← registers `vector` as a
│                                       installable package
└── tests/                           ← existing Hermes tests
```

`vector` is a regular Python package under the `hermes-agent` monorepo.
It can `import` from `agent`, `tools`, `gateway`, etc. without ceremony —
integration tests against the real Hermes code are now trivial to write.

## Conventions

- **Python ≥ 3.11.** Hermes runs on 3.11+. We use stdlib only for the
  core; `pyyaml` and `httpx` are optional imports behind a feature flag.
- **Public API is async-first.** `AgentRuntime.run`, `dispatcher.dispatch`,
  `Channel.post` are `async def`. Sync wrappers are explicit
  (`Runtime.run_sync`).
- **State lives in `state.db` (SQLite + FTS5).** Same shape Hermes
  already uses for sessions.
- **Secrets stay in `.env`.** Settings stay in `config.yaml`. We never
  put a non-credential value in `.env`.
- **Português (pt-BR)** em comentários e mensagens voltadas ao usuário;
  inglês em código, docstrings, e commit messages.
- **Conventional Commits** + DCO (`-s`).
- **PR titles** seguem o padrão do projeto:
  `feat(<scope>): <description> (PR-NNN)` — sem emoji, sem nome de
  vendor, sem tema.

## Model / Provider Resolution

Every agent has its own `model` and `provider`. Resolution order
(first non-null wins):

1. `AgentProfile.model` + `AgentProfile.provider` — most specific.
2. `Channel.default_model` — per-channel override (future).
3. `vector.defaults.model` in `~/.hermes/config.yaml`.
4. The current Hermes session model — least specific.

When the primary model fails with a **transient** error
(rate-limit, 5xx, network timeout, OOM), `AgentRuntime` walks
`profile.fallback_models` in order. **Non-transient** errors
(auth, validation) short-circuit — no fallback. If all attempts
fail, the run returns `status="error"` with a chain summary.

Model / provider values are validated against the **live Hermes
provider catalog** (`hermes model list`). Unknown values raise
`UnknownModelError` at construction time, not at run time.

## Channel Limits

| Channel type | Member cap | Configurable |
|---|---|---|
| `stream` / `workflow` | soft=50, hard=200 | yes (`vector.channel_limits.{soft,hard}`) |
| `dm` | exactly 2 | no (fixed by type) |

Soft cap emits a warning but allows the add. Hard cap rejects with
`ChannelTooLargeError`. Limits count humans + agents together.
Atomic team-add (`add-team`) rolls back on any violation.

## Verification (per PR)

Two layers — a **lightweight ubuntu-latest CI** for reviewable gates
and a **local verifier** that produces the JSON evidence.

### CI (`ubuntu-latest`, ≤ 3 min/job)

The contract workflow lives at
`.github/workflows/contract.yml`. Three jobs, each capped at 3
minutes, run on `ubuntu-latest`:

- `lint` — `ruff check src tests scripts`.
- `test` — `pytest -v --strict-markers`.
- `contract` — `verify-feature.sh` for every implemented feature,
  uploads `.spec/verification/*.json` as an artefact.

The jobs are deliberately small and short so they cost almost
nothing against the monthly Actions minutes budget. No matrix
builds, no caching, no multi-OS — just the three gates above.

### Local (the authoritative source of evidence)

```bash
# 1. Lint
.venv/Scripts/python.exe -m ruff check src tests scripts

# 2. Full test suite
.venv/Scripts/python.exe -m pytest -v --strict-markers

# 3. Contract verifier for each implemented feature
sh scripts/verify-feature.sh pr-NNN-<slug> --json \
  > .spec/verification/pr-NNN-<slug>.json
```

A PR só é considerada entregue quando:

1. `ruff check` exits 0.
2. `pytest -v --strict-markers` is all-green.
3. `verify-feature.sh` exits 0 with `status: pass` in the JSON,
   covering every `@spec:AC-VEC-NNN` listed in the spec.
4. CI shows the three jobs green on the PR.
5. The draft `PR-NNN-<slug>.md` in `docs/roadmap/prs/` is closed
   with a comment pointing at the real implementation PR.

The JSON evidence files under `.spec/verification/` are committed
alongside the implementation so reviewers can inspect them
without re-running the verifier.
