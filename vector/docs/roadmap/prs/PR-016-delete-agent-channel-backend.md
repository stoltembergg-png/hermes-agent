# PR-016: Delete agent + delete channel (backend)

## Depends on
PR-014

## Problem
The backend has no delete operations. Once an agent or channel is created, it cannot be removed. This blocks testing (can't delete a duplicate agent) and real usage (can't remove stale channels).

## Requirements

### REQ-VEC-016-1: DELETE /agents/{handle}
Add `DELETE /agents/{handle}` endpoint to `plugin_api.py` that:
- Removes the agent from the registry (`agents.yaml`)
- Removes the agent's memberships from all channels
- Does NOT delete the agent's posted messages (keep history)
- Returns `{"deleted": true, "handle": "<handle>"}` on success

### REQ-VEC-016-2: DELETE /channels/{id}
Add `DELETE /channels/{id}` endpoint to `plugin_api.py` that:
- Deletes the channel + all its messages + all its memberships (cascade)
- Returns `{"deleted": true, "channel_id": "<id>"}` on success

### REQ-VEC-016-3: Service layer delete methods
Add to `VectorService`:
- `delete_agent(handle: str) -> bool` — calls `registry.remove(handle)` + `store.remove_member_all(handle)`
- `delete_channel(channel_id: str) -> bool` — calls `store.delete_channel(channel_id)`
The dispatcher and runtime references SHOULD be kept (they can be recreated on next use).

### REQ-VEC-016-4: AgentRegistry remove method
Add `AgentRegistry.remove(handle: str)` — removes from YAML + in-memory dict. Throws `AgentNotFoundError` if handle doesn't exist.

### REQ-VEC-016-5: ChannelStore delete methods
Add to `ChannelStore`:
- `delete_channel(channel_id: str)` — DELETE FROM channels, memberships, messages WHERE channel_id = ?
- `remove_member_all(handle: str)` — DELETE FROM memberships WHERE member_handle = ?

## Acceptance Criteria

- AC-VEC-016-1: `DELETE /agents/gandalf` removes agent from registry and all channel memberships
- AC-VEC-016-2: `DELETE /channels/{id}` removes channel + messages + memberships
- AC-VEC-016-3: Deleting non-existent agent returns 404 with `VECTOR_AGENT_NOT_FOUND`
- AC-VEC-016-4: Agent's posted messages survive agent deletion (only memberships removed)
- AC-VEC-016-5: After deleting an agent, `list_members` for channels they were in no longer includes the handle

## Implementation Plan

### Files
- `vector/src/vector/profile.py` (~+20 LoC) — add `AgentRegistry.remove`
- `vector/src/vector/channel.py` (~+30 LoC) — add `delete_channel`, `remove_member_all`
- `vector/src/vector/service.py` (~+20 LoC) — add `delete_agent`, `delete_channel`
- `plugins/vector-channels/dashboard/plugin_api.py` (~+40 LoC) — add DELETE endpoints
- `vector/tests/` — contract tests

### Steps
1. `profile.py`: Add `AgentRegistry.remove(handle)`:
   - Pop from `self._agents` dict → if missing raise `AgentNotFoundError`
   - Save updated YAML
2. `channel.py`: Add `ChannelStore.delete_channel(channel_id)`:
   - SQL: `DELETE FROM messages WHERE channel_id = ?`
   - SQL: `DELETE FROM memberships WHERE channel_id = ?`
   - SQL: `DELETE FROM channels WHERE id = ?`
3. `channel.py`: Add `ChannelStore.remove_member_all(handle)`:
   - SQL: `DELETE FROM memberships WHERE member_handle = ?`
4. `service.py`: Add `delete_agent(handle)`:
   - Call `self._registry.remove(handle)`
   - Call `self._store.remove_member_all(handle)`
5. `service.py`: Add `delete_channel(channel_id)`:
   - Verify channel exists → call `self._store.delete_channel(channel_id)`
6. `plugin_api.py`: Add `DELETE /agents/{handle}` and `DELETE /channels/{id}` route handlers

test_file: tests/test_pr_016.py
