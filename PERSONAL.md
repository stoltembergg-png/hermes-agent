# Personal Working Copy — Hermes Agent

> ⚠️ This repository is a **personal working copy** of
> [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent).
> It is **not** a fork and is **not** affiliated with Nous Research.

## Purpose

This copy exists solely as a **read reference** for the
[`vector`](../vector) project
([stoltembergg-png/vector](https://github.com/stoltembergg-png/vector)) —
a multi-agent orchestration layer that wraps Hermes Agent's
`delegate_task` tool, `gateway` IPC, and Desktop plugin API.

`vector` design specs in `docs/roadmap/prs/PR-NNN-*.md` cite specific
files and line numbers from this repository (and from the upstream
[`NousResearch/hermes-agent`](https://github.com/NousResearch/hermes-agent))
as authoritative references for the contracts `vector` adapts.

## Sync policy

- This copy is **kept in sync** with the upstream `main` branch by
  manual `git pull --ff-only` only. No PRs are opened against
  `stoltembergg-png/hermes-agent` itself.
- No commits are made on `main` here. If local notes are needed, they
  go on a topic branch (`note/...`) and are never merged into `main`.
- The remote `origin` points to `stoltembergg-png/hermes-agent`. The
  upstream `NousResearch/hermes-agent` is added as a second remote
  named `upstream` for `fetch` only.

## Relationship with `vector`

```
stoltembergg-png/vector          (this is what we build)
        │
        │  reads contracts from
        ▼
stoltembergg-png/hermes-agent    (read-only mirror)
        │
        │  mirrors
        ▼
NousResearch/hermes-agent        (upstream)
```

## License

This copy inherits the upstream MIT license. See [`LICENSE`](./LICENSE).
All credit for the code goes to the original authors and Nous Research.
