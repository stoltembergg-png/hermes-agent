# PR-003 — Channel Store (SQLite)

> **Status:** planned · **Depends on:** PR-001 (uses `AgentProfile.handle`) · **Estimated size:** ~250 LoC

## Goal

A `ChannelStore` backed by SQLite that persists:

- Channels (id, name, visibility, type, created_at).
- Membership (channel_id, member_handle, joined_at).
- Messages (id, channel_id, author_handle, body, mentions_json, created_at).

Same DB layout pattern as Hermes' own `state.db` (SQLite + FTS5).
FTS5 index on `messages.body` for fast `@handle` and full-text search.

## Requirements

- **REQ-VEC-003-1.** `Channel` MUST have `id`, `name` (unique, slug),
  `visibility` (`open` | `private`), `type` (`stream` | `dm` |
  `workflow`), `created_at`, `member_limit_soft` (int, default 50),
  `member_limit_hard` (int, default 200).
- **REQ-VEC-003-2.** `ChannelStore.create(c)` MUST persist and return
  the canonical channel.
- **REQ-VEC-003-3.** `ChannelStore.add_member(channel_id, handle)` MUST
  raise `NotAMemberError` if `handle` is not a registered agent
  profile (consumed via `AgentRegistry` from PR-001).
- **REQ-VEC-003-4.** `ChannelStore.post(channel_id, author, body)` MUST
  extract mentions via `mention.extract_mentions`, store them in
  `mentions_json`, and return the `Message`.
- **REQ-VEC-003-5.** `ChannelStore.history(channel_id, limit=50,
  before_id=None)` MUST return messages in chronological order.
- **REQ-VEC-003-6.** A FTS5 virtual table MUST index `messages.body`
  and `ChannelStore.search(channel_id, query)` MUST return matches
  ordered by rank.
- **REQ-VEC-003-7.** `add_member` MUST enforce member limits:
  - If `len(members) + 1 > member_limit_hard`: raise
    `ChannelTooLargeError`.
  - If `len(members) + 1 >= member_limit_soft`: log a warning but
    succeed.
  - Limits are configurable via `vector.channel_limits.{soft,hard}` in
    `config.yaml` (default 50/200).
- **REQ-VEC-003-8.** `ChannelType.dm` MUST have a fixed member count of
  exactly 2 (creator + one other). Adding a third member to a `dm`
  raises `DmChannelFullError`.

## Acceptance criteria

- `AC-VEC-003-1` — `create(Channel(name="dev-room"))` round-trips: a
  fresh `get("dev-room")` returns an equal object.
- `AC-VEC-003-2` — `add_member(c, "gandalf")` raises
  `DuplicateMembershipError` if already a member.
- `AC-VEC-003-3` — `add_member(c, "ghost")` raises
  `NotAMemberError` if no profile `ghost` is registered.
- `AC-VEC-003-4` — `post(c, "you", "@gandalf please review")` produces
  a `Message` with `mentions == ["gandalf"]`.
- `AC-VEC-003-5` — `history(c)` after three posts returns exactly
  those three, oldest first.
- `AC-VEC-003-6` — `search(c, "review")` returns messages containing
  the word, ranked by FTS5.
- `AC-VEC-003-7` — `add_member` on a channel with 50 members (soft cap)
  succeeds and emits a warning log; on 200 members (hard cap) raises
  `ChannelTooLargeError`.
- `AC-VEC-003-8` — `create(Channel(type="dm"))` accepts exactly 2
  members; adding a third to a DM channel raises `DmChannelFullError`.

## Files

- `src/vector/channel.py` — new module (Channel, Membership, Message,
  ChannelStore)
- `tests/test_channel.py` — contract tests, one per AC
- Uses an in-memory or temp-file SQLite fixture (`tmp_path`).

## Out of scope

- Cross-host replication (PR in v1).
- Encryption of message bodies (v1).
