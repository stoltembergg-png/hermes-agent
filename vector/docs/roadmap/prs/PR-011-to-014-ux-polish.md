# Vector UX Polish — PR Breakdown

## Problems to fix

1. **Bug**: Selecting a channel does nothing (`loadChannelData` runs but UI doesn't react — `activeChannel` is set but the `messages` array is empty, no visible change)
2. **Bug**: Agent creation errors (duplicate handle) shown as raw JSON instead of clean error
3. **Missing**: No provider/model picker per agent — backend supports `model` + `provider` fields but UI doesn't expose them
4. **UX**: Interface is confusing — buttons have same icon (two `add` icons), no visual distinction between "Add Agent" and "Create Channel", no agent list visible, no member list in channel view

## PR Plan

### PR-011: Fix channel selection + message display
**Scope**: `plugin.tsx` only

- Fix `loadChannelData` — display messages IMMEDIATELY after selecting channel (even if empty)
- Show "No messages yet. Start chatting below." when channel is selected but has zero messages
- Show channel name + member list as header in the message area
- Auto-scroll to bottom on new messages
- Fix `postAndDispatch` — merge new messages into existing list, don't replace

**AC**: When user clicks a channel, the message area shows the channel name, member list, and message history (or empty state). Posting a message appends it to the list.

---

### PR-012: Error handling + agent model picker
**Scope**: `plugin.tsx`, `api.ts`, `plugin_api.py`

- Parse error JSON (`{"error":{"code":"...","message":"..."}}`) in catch blocks and show only the `message` field
- Add provider/model picker to AddAgentModal:
  - Fetch model catalog from `/api/model/options` (existing backend endpoint)
  - Provider dropdown + Model dropdown
  - Optional fields — defaults to "Inherit from session"
- Fix button icons: robot for Add Agent, comment-discussion for Create Channel (currently both use `add`)

**AC**: Agent creation with duplicate handle shows clean error "Agent 'gandalf' already exists". AddAgentModal has provider + model dropdowns populated from backend.

---

### PR-013: Agent list + channel details panel
**Scope**: `plugin.tsx`, `vector-channels.css`

- Show registered agents with avatar + handle + model in a sidebar section below Channels
- Click agent → shows agent details (system prompt, model, provider) in a panel
- Channel header shows channel name + member avatars + leave/delete buttons
- Member list visible in channel view (not just in creation modal)

**AC**: Sidebar shows list of channels AND list of agents. Channel view header shows name + all members with @handles. Agent selection shows profile details.

---

### PR-014: Delete agent + delete channel
**Scope**: `plugin_api.py`, `api.ts`, `plugin.tsx`, `service.py`

- `DELETE /agents/{handle}` — remove agent from registry, remove from all channel memberships
- `DELETE /channels/{id}` — delete channel + all messages + memberships
- UI: trash icon on agent row, trash icon on channel header (with confirm modal)
- Cascading delete: removing agent removes their messages? No — keep messages, just remove membership

**AC**: User can delete an agent (with confirm). User can delete a channel (with confirm). Deleting agent removes them from all channel memberships but keeps their posted messages.
