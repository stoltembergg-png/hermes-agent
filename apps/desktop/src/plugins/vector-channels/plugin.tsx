/**
 * Vector Channels — multi-agent conversation panel for Hermes Desktop.
 *
 * Implements PR-007 + PR-009 of the vector roadmap. Registers a sidebar
 * nav row + a `/vector` route that renders the channel browser, message
 * history, and a composer that posts via the backend dispatcher.
 *
 * Ships OFF by default (`defaultEnabled: false`).
 * REST calls live in ./api.ts and target /api/vector/*.
 */

import './vector-channels.css'

import {
  atom,
  cn,
  Codicon,
  type HermesPlugin,
  host,
  PALETTE_AREA,
  type PaletteContribution,
  type RouteContribution,
  ROUTES_AREA,
  SIDEBAR_NAV_AREA,
  type SidebarNavContribution,
  STATUSBAR_AREAS,
  useValue,
} from '@hermes/plugin-sdk'
import { type ChangeEvent, type KeyboardEvent, useEffect, useRef, useState } from 'react'

import {
  type AgentInfo,
  bindApi,
  type ChannelInfo,
  createAgent,
  createChannel,
  deleteAgent,
  getHealth,
  getHistory,
  getMembers,
  getModelOptions,
  listAgents,
  listChannels,
  type MessageInfo,
  type ModelOptionProvider,
  parseApiError,
  postMessage,
  type RestFn,
} from './api'

// ---------------------------------------------------------------------------
// State atoms (plugin-local nanostores)
// ---------------------------------------------------------------------------

const $channels = atom<ChannelInfo[]>([])
const $activeChannel = atom<string | null>(null)
const $channelName = atom<string | null>(null)
const $messages = atom<MessageInfo[]>([])
const $unread = atom<Record<string, number>>({})
const $members = atom<string[]>([])
const $agents = atom<string[]>([])
const $agentDetails = atom<AgentInfo[]>([])
const $selectedAgent = atom<string | null>(null)
const $composer = atom('')
const $autocomplete = atom<string[]>([])
const $loading = atom(false)
const $error = atom<string | null>(null)
const $showCreateChannel = atom(false)
const $showAddAgent = atom(false)

// ---------------------------------------------------------------------------
// Autocomplete logic (REQ-VEC-007-5)
// ---------------------------------------------------------------------------

function computeAutocomplete(text: string, members: string[]): string[] {
  const match = text.match(/@(\w+)$/)

  if (!match) {
    return []
  }

  const partial = match[1].toLowerCase()

  return members.filter(m => m.toLowerCase().startsWith(partial))
}

// ---------------------------------------------------------------------------
// Unread badge logic (REQ-VEC-007-2)
// ---------------------------------------------------------------------------

function markRead(channelId: string): void {
  const unread = { ...$unread.get() }
  delete unread[channelId]
  $unread.set(unread)
}

function incrementUnread(channelId: string): void {
  const unread = { ...$unread.get() }
  unread[channelId] = (unread[channelId] ?? 0) + 1
  $unread.set(unread)
}

function totalUnread(): number {
  return Object.values($unread.get()).reduce((a, b) => a + b, 0)
}

// ---------------------------------------------------------------------------
// Components
// ---------------------------------------------------------------------------

function ChannelRow({ channel }: { channel: ChannelInfo }) {
  const active = useValue($activeChannel)
  const unread = useValue($unread)
  const count = unread[channel.id] ?? 0
  const isActive = active === channel.id

  return (
    <button
      className={cn(
        'flex w-full items-center justify-between rounded-md px-3 py-1.5 text-sm transition-colors',
        isActive
          ? 'bg-(--ui-bg-active) text-foreground'
          : 'text-(--ui-text-secondary) hover:bg-(--chrome-action-hover)',
      )}
      data-testid={`vector-channel-${channel.name}`}
      onClick={() => {
        $activeChannel.set(channel.id)
        $channelName.set(channel.name)
        markRead(channel.id)
        void loadChannelData(channel.id)
      }}
      type="button"
    >
      <span className="flex items-center gap-1.5">
        <Codicon name="comment-discussion" size="0.75rem" />
        <span>{channel.name}</span>
      </span>
      {count > 0 && (
        <span className="rounded-full bg-(--ui-accent) px-1.5 text-[0.625rem] tabular-nums text-white">
          {count}
        </span>
      )}
    </button>
  )
}

function MessageRow({ msg }: { msg: MessageInfo }) {
  return (
    <div className="message-row" data-testid={`vector-message-${msg.author_handle}`}>
      <span className="message-author">@{msg.author_handle}</span>
      <span className="message-time">{new Date(msg.created_at).toLocaleTimeString()}</span>
      <p className="message-body">{msg.body}</p>
    </div>
  )
}

function Composer() {
  const value = useValue($composer)
  const suggestions = useValue($autocomplete)
  const activeChannel = useValue($activeChannel)

  const handleInput = (e: ChangeEvent<HTMLInputElement>) => {
    const text = e.target.value
    $composer.set(text)
    const members = $members.get()
    $autocomplete.set(computeAutocomplete(text, members))
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && activeChannel && value.trim()) {
      e.preventDefault()
      void postAndDispatch(activeChannel, value.trim())
      $composer.set('')
      $autocomplete.set([])
    }
  }

  return (
    <div className="composer" data-testid="vector-composer">
      {suggestions.length > 0 && (
        <div className="autocomplete-list">
          {suggestions.map(s => (
            <button
              className="autocomplete-item"
              key={s}
              onClick={() => {
                const text = $composer.get().replace(/@(\w+)$/, `@${s} `)
                $composer.set(text)
                $autocomplete.set([])
              }}
              type="button"
            >
              @{s}
            </button>
          ))}
        </div>
      )}
      <input
        className="composer-input"
        onChange={handleInput}
        onKeyDown={handleKeyDown}
        placeholder="Type a message... use @handle to mention agents"
        value={value}
      />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Create Channel modal
// ---------------------------------------------------------------------------

function CreateChannelModal() {
  const agents = useValue($agents)
  const [name, setName] = useState('')
  const [selectedAgents, setSelectedAgents] = useState<string[]>([])
  const [creating, setCreating] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const toggleAgent = (handle: string) => {
    setSelectedAgents(prev =>
      prev.includes(handle) ? prev.filter(a => a !== handle) : [...prev, handle],
    )
  }

  const handleCreate = async () => {
    if (!name.trim()) {
      return
    }

    setCreating(true)
    setErr(null)

    try {
      await createChannel(name.trim(), ['human', ...selectedAgents])
      $showCreateChannel.set(false)
      // Refresh channels
      const chs = await listChannels()
      $channels.set(chs)
      setName('')
      setSelectedAgents([])
    } catch (e) {
      setErr(parseApiError(e))
    } finally {
      setCreating(false)
    }
  }

  return (
    <div className="vector-modal-backdrop" onClick={() => $showCreateChannel.set(false)}>
      <div className="vector-modal" data-testid="vector-create-channel-modal" onClick={e => e.stopPropagation()}>
        <div className="vector-modal-header">
          <h3>Create Channel</h3>
          <button className="vector-modal-close" onClick={() => $showCreateChannel.set(false)} type="button">
            <Codicon name="close" />
          </button>
        </div>
        <div className="vector-modal-body">
          <label className="vector-modal-label">
            Channel name
            <input
              autoFocus
              className="vector-modal-input"
              onChange={e => setName(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleCreate()}
              placeholder="e.g. dev-team"
              value={name}
            />
          </label>
          {agents.length > 0 && (
            <div className="vector-modal-label">
              <span>Agent members</span>
              <div className="vector-agent-picker">
                {agents.map(a => (
                  <button
                    className={cn(
                      'vector-agent-chip',
                      selectedAgents.includes(a) && 'vector-agent-chip-selected',
                    )}
                    key={a}
                    onClick={() => toggleAgent(a)}
                    type="button"
                  >
                    @{a}
                  </button>
                ))}
              </div>
            </div>
          )}
          {agents.length === 0 && (
            <p className="vector-modal-hint">
              No agents registered yet. Use the "Add Agent" button to create one first,
              or just create the channel with only yourself as a member.
            </p>
          )}
          {err && <p className="vector-modal-error">{err}</p>}
        </div>
        <div className="vector-modal-footer">
          <button className="vector-btn-secondary" onClick={() => $showCreateChannel.set(false)} type="button">
            Cancel
          </button>
          <button
            className="vector-btn-primary"
            disabled={!name.trim() || creating}
            onClick={handleCreate}
            type="button"
          >
            {creating ? 'Creating...' : 'Create'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Add Agent modal
// ---------------------------------------------------------------------------

function AddAgentModal() {
  const [handle, setHandle] = useState('')
  const [prompt, setPrompt] = useState('')
  const [creating, setCreating] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  // PR-013: provider/model picker state. Empty string === "inherit
  // session defaults" (omitted from the createAgent request entirely).
  const [providers, setProviders] = useState<ModelOptionProvider[]>([])
  const [provider, setProvider] = useState('')
  const [model, setModel] = useState('')

  // Fetch the Hermes model catalog once on modal mount so the Advanced
  // dropdowns are populated. A fetch failure is non-fatal — the user can
  // still create an agent with session-inherited defaults (both selects
  // just stay empty).
  useEffect(() => {
    let cancelled = false
    void getModelOptions()
      .then(res => {
        if (cancelled) {
          return
        }

        setProviders(res.providers)
      })
      .catch(() => {
        // Catalog unavailable — silently leave the dropdowns empty.
      })

    return () => {
      cancelled = true
    }
  }, [])

  // Models for the currently-selected provider (empty until one is picked).
  const modelOptions = providers.find(p => p.slug === provider)?.models ?? []

  const handleCreate = async () => {
    if (!handle.trim() || !prompt.trim()) {
      return
    }

    setCreating(true)
    setErr(null)

    try {
      // Omit model/provider when empty so the backend uses session defaults
      // (createAgent already types them as optional).
      const req: Parameters<typeof createAgent>[0] = {
        handle: handle.trim(),
        system_prompt: prompt.trim(),
      }

      if (provider) {
        req.provider = provider
      }

      if (model) {
        req.model = model
      }

      await createAgent(req)
      // Refresh agents
      const agentList = await listAgents()
      $agentDetails.set(agentList)
      $agents.set(agentList.map(a => a.handle))
      $showAddAgent.set(false)
      setHandle('')
      setPrompt('')
      setProvider('')
      setModel('')
    } catch (e) {
      setErr(parseApiError(e))
    } finally {
      setCreating(false)
    }
  }

  return (
    <div className="vector-modal-backdrop" onClick={() => $showAddAgent.set(false)}>
      <div className="vector-modal" data-testid="vector-add-agent-modal" onClick={e => e.stopPropagation()}>
        <div className="vector-modal-header">
          <h3>Add Agent</h3>
          <button className="vector-modal-close" onClick={() => $showAddAgent.set(false)} type="button">
            <Codicon name="close" />
          </button>
        </div>
        <div className="vector-modal-body">
          <label className="vector-modal-label">
            Handle (unique name)
            <input
              autoFocus
              className="vector-modal-input"
              onChange={e => setHandle(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleCreate()}
              placeholder="e.g. gandalf, researcher, coder"
              value={handle}
            />
          </label>
          <label className="vector-modal-label">
            System prompt
            <textarea
              className="vector-modal-input"
              onChange={e => setPrompt(e.target.value)}
              placeholder="e.g. You are a wise assistant. Answer concisely."
              rows={3}
              value={prompt}
            />
          </label>
          <details className="vector-modal-details" data-testid="vector-add-agent-advanced">
            <summary>Advanced</summary>
            <label className="vector-modal-label">
              Provider
              <select
                className="vector-modal-input"
                data-testid="vector-add-agent-provider"
                onChange={e => {
                  setProvider(e.target.value)
                  // Reset model when the provider changes so we never submit a
                  // stale model that doesn't belong to the new provider.
                  setModel('')
                }}
                value={provider}
              >
                <option value="">Inherit from session</option>
                {providers.map(p => (
                  <option key={p.slug} value={p.slug}>{p.name}</option>
                ))}
              </select>
            </label>
            <label className="vector-modal-label">
              Model
              <select
                className="vector-modal-input"
                data-testid="vector-add-agent-model"
                disabled={!provider}
                onChange={e => setModel(e.target.value)}
                value={model}
              >
                <option value="">Inherit</option>
                {modelOptions.map(m => (
                  <option key={m} value={m}>{m}</option>
                ))}
              </select>
            </label>
          </details>
          {err && <p className="vector-modal-error">{err}</p>}
        </div>
        <div className="vector-modal-footer">
          <button className="vector-btn-secondary" onClick={() => $showAddAgent.set(false)} type="button">
            Cancel
          </button>
          <button
            className="vector-btn-primary"
            disabled={!handle.trim() || !prompt.trim() || creating}
            onClick={handleCreate}
            type="button"
          >
            {creating ? 'Creating...' : 'Create Agent'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Sidebar with action buttons
// ---------------------------------------------------------------------------

function SidebarHeader() {
  return (
    <div className="vector-sidebar-header">
      <h2 className="sidebar-title">Channels</h2>
      <div className="vector-sidebar-actions">
        <button
          className="vector-icon-btn"
          onClick={() => void refreshAgents()}
          title="Add Agent"
          type="button"
        >
          <Codicon name="robot" size="0.875rem" />
        </button>
        <button
          className="vector-icon-btn"
          onClick={() => $showAddAgent.set(true)}
          title="Add Agent"
          type="button"
        >
          <Codicon name="add" size="0.875rem" />
        </button>
        <button
          className="vector-icon-btn"
          onClick={() => $showCreateChannel.set(true)}
          title="Create Channel"
          type="button"
        >
          <Codicon name="add" size="0.875rem" />
        </button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Data loading helpers
// ---------------------------------------------------------------------------

async function refreshAgents(): Promise<void> {
  try {
    const agentList = await listAgents()
    $agentDetails.set(agentList)
    $agents.set(agentList.map(a => a.handle))
  } catch {
    // Non-fatal
  }
}

async function deleteAgentAndRefresh(handle: string): Promise<void> {
  await deleteAgent(handle)
  await refreshAgents()
}

async function loadChannelData(channelId: string): Promise<void> {
  $loading.set(true)

  try {
    const [history, members] = await Promise.all([
      getHistory(channelId, 50),
      getMembers(channelId),
    ])

    $messages.set(history)
    $members.set(members)
    // Set channel name from $channels lookup
    const chs = $channels.get()
    const ch = chs.find(c => c.id === channelId)

    if (ch) {
      $channelName.set(ch.name)
    }
  } finally {
    $loading.set(false)
  }
}

async function postAndDispatch(channelId: string, body: string): Promise<void> {
  $loading.set(true)

  try {
    const result = await postMessage(channelId, 'human', body, true)
    const allMsgs = result.messages

    if (allMsgs.length > 0) {
      // Merge: dedup by message ID, preserving order
      const existing = $messages.get()
      const ids = new Set(existing.map(m => m.id))
      const newMsgs = allMsgs.filter(m => !ids.has(m.id))
      $messages.set([...existing, ...newMsgs])
    } else {
      const msgs = $messages.get()
      const ids = new Set(msgs.map(m => m.id))

      if (!ids.has(result.message.id)) {
        $messages.set([...msgs, result.message])
      }
    }
  } catch {
    // Error state — non-fatal, preserves existing messages
  } finally {
    $loading.set(false)
  }
}

// ---------------------------------------------------------------------------
// Channel header — shows channel name + member chips
// ---------------------------------------------------------------------------

function ChannelHeader() {
  const channelName = useValue($channelName)
  const members = useValue($members)

  if (!channelName) {
    return null
  }

  return (
    <div className="vector-channel-header" data-testid="vector-channel-header">
      <h3 className="vector-channel-name">
        <Codicon name="comment-discussion" size="0.875rem" />
        {channelName}
      </h3>
      <div className="vector-channel-members">
        <span className="vector-member-count">{members.length} members</span>
        {members.map(m => (
          <span className="vector-member-chip" key={m}>
            <Codicon name={m === 'human' ? 'account' : 'robot'} size="0.625rem" />
            @{m}
          </span>
        ))}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// PR-014: Agent list sidebar section + details panel
// ---------------------------------------------------------------------------

function agentModelLabel(agent: AgentInfo): string {
  return agent.model ?? '--inherit--'
}

function AgentRow({ agent }: { agent: AgentInfo }) {
  const selectedAgent = useValue($selectedAgent)
  const isActive = selectedAgent === agent.handle

  return (
    <div
      className={cn(
        'vector-agent-row',
        isActive && 'vector-agent-row-active',
      )}
      data-testid={`vector-agent-${agent.handle}`}
    >
      <button
        className="vector-agent-row-main"
        onClick={() => {
          $selectedAgent.set(agent.handle)
          // Deselect any active channel so the details panel replaces it.
          $activeChannel.set(null)
        }}
        type="button"
      >
        <Codicon name="robot" size="0.75rem" />
        <span className="vector-agent-handle">@{agent.handle}</span>
        <span className="vector-agent-model">{agentModelLabel(agent)}</span>
      </button>
      <button
        className="vector-agent-row-delete"
        data-testid={`vector-agent-${agent.handle}-delete`}
        onClick={() => void deleteAgentAndRefresh(agent.handle)}
        title="Delete agent"
        type="button"
      >
        <Codicon name="trash" size="0.75rem" />
      </button>
    </div>
  )
}

function AgentDetails({ agent }: { agent: AgentInfo }) {
  const channels = useValue($channels)
  const loading = useValue($loading)
  const [memberships, setMemberships] = useState<string[]>([])
  const [deleting, setDeleting] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  // Compute channel memberships: which channels list this agent as a member.
  useEffect(() => {
    let cancelled = false

    void (async () => {
      const result: string[] = []

      for (const ch of channels) {
        try {
          const members = await getMembers(ch.id)

          if (members.includes(agent.handle)) {
            result.push(ch.name)
          }
        } catch {
          // Non-fatal — skip this channel
        }
      }

      if (!cancelled) {
        setMemberships(result)
      }
    })()

    return () => {
      cancelled = true
    }
  }, [agent.handle, channels])

  const handleDelete = async () => {
    setDeleting(true)
    setErr(null)

    try {
      await deleteAgent(agent.handle)
      $selectedAgent.set(null)
      await refreshAgents()
    } catch (e) {
      setErr(parseApiError(e))
    } finally {
      setDeleting(false)
    }
  }

  const promptText = agent.description || '(not set)'
  const modelText = agent.model ?? '--inherit--'
  const providerText = agent.provider ?? '--inherit--'

  return (
    <div className="vector-agent-details" data-testid={`vector-agent-details-${agent.handle}`}>
      <div className="vector-agent-details-header">
        <h3 className="vector-agent-details-title">
          <Codicon name="robot" size="1rem" />
          @{agent.handle}
        </h3>
        <button
          className="vector-btn-primary"
          data-testid="vector-agent-details-delete"
          disabled={deleting}
          onClick={handleDelete}
          type="button"
        >
          <Codicon name="trash" size="0.75rem" /> {deleting ? 'Deleting...' : 'Delete Agent'}
        </button>
      </div>
      {err && <p className="vector-modal-error">{err}</p>}
      <dl className="vector-agent-details-grid">
        <dt>System prompt</dt>
        <dd className="vector-agent-details-prompt">{promptText}</dd>
        <dt>Model</dt>
        <dd>
          <span className="vector-agent-details-value">{modelText}</span>
        </dd>
        <dt>Provider</dt>
        <dd>
          <span className="vector-agent-details-value">{providerText}</span>
        </dd>
        <dt>Channel memberships</dt>
        <dd>
          {loading && memberships.length === 0 ? (
            <span className="vector-agent-details-muted">Loading...</span>
          ) : memberships.length === 0 ? (
            <span className="vector-agent-details-muted">(none)</span>
          ) : (
            <ul className="vector-agent-memberships">
              {memberships.map(name => (
                <li className="vector-agent-membership-chip" key={name}>
                  <Codicon name="comment-discussion" size="0.625rem" />
                  {name}
                </li>
              ))}
            </ul>
          )}
        </dd>
      </dl>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

function ChannelsPage() {
  const channels = useValue($channels)
  const messages = useValue($messages)
  const activeChannel = useValue($activeChannel)
  const loading = useValue($loading)
  const error = useValue($error)
  const showCreateChannel = useValue($showCreateChannel)
  const showAddAgent = useValue($showAddAgent)
  const agents = useValue($agents)
  const agentDetails = useValue($agentDetails)
  const selectedAgent = useValue($selectedAgent)

  const messageListRef = useRef<HTMLDivElement>(null)

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    if (messageListRef.current) {
      messageListRef.current.scrollTop = messageListRef.current.scrollHeight
    }
  }, [messages])

  useEffect(() => {
    void (async () => {
      $loading.set(true)
      $error.set(null)

      try {
        // Check if the vector API is reachable
        await getHealth()
        const [chs, agentList] = await Promise.all([listChannels(), listAgents()])
        $channels.set(chs)
        $agentDetails.set(agentList)
        $agents.set(agentList.map(a => a.handle))
      } catch {
        $error.set('Vector API not reachable. Make sure the Hermes backend is running (hermes serve or hermes dashboard).')
      } finally {
        $loading.set(false)
      }
    })()
  }, [])

  return (
    <div className="vector-page" data-testid="vector-nav">
      <aside className="vector-sidebar" data-testid="vector-channel-list">
        <SidebarHeader />
        {channels.map(ch => (
          <ChannelRow channel={ch} key={ch.id} />
        ))}
        {channels.length === 0 && !loading && !error && (
          <div className="vector-empty-mini">
            <p>No channels yet.</p>
            <button
              className="vector-btn-primary vector-btn-sm"
              onClick={() => $showCreateChannel.set(true)}
              type="button"
            >
              <Codicon name="add" size="0.75rem" /> Create Channel
            </button>
          </div>
        )}
        {agentDetails.length > 0 && (
          <div className="vector-agents-section" data-testid="vector-agents-section">
            <div className="vector-agents-header">Agents</div>
            {agentDetails.map(a => (
              <AgentRow agent={a} key={a.handle} />
            ))}
          </div>
        )}
      </aside>
      <main className="vector-main">
        {error ? (
          <div className="vector-error-state" data-testid="vector-error-state">
            <Codicon name="error" size="2rem" />
            <p className="vector-error-title">{error}</p>
            <div className="vector-error-help">
              <h4>Quick start</h4>
              <ol>
                <li>In a terminal, run: <code>hermes serve</code></li>
                <li>Click the <Codicon name="add" size="0.75rem" /> button in the sidebar to register an agent</li>
                <li>Click the <Codicon name="new-file" size="0.75rem" /> button to create a channel</li>
                <li>Select the channel and start chatting — use <code>@handle</code> to mention agents</li>
              </ol>
            </div>
          </div>
        ) : selectedAgent ? (
          <AgentDetails agent={agentDetails.find(a => a.handle === selectedAgent) ?? agentDetails[0]} />
        ) : activeChannel ? (
          <>
            <ChannelHeader />
            <div className="message-list" data-testid="vector-message-list" ref={messageListRef}>
              {messages.length === 0 && !loading && (
                <div className="vector-no-messages" data-testid="vector-no-messages">
                  <Codicon name="comment-discussion" size="1.5rem" />
                  <p>No messages yet.</p>
                  <p className="vector-hint">Start chatting below — use @handle to mention agents</p>
                </div>
              )}
              {messages.map(msg => (
                <MessageRow key={msg.id} msg={msg} />
              ))}
              {loading && <p className="text-(--ui-text-tertiary)">Loading...</p>}
            </div>
            <Composer />
          </>
        ) : (
          <div className="empty-state">
            <Codicon name="comment-discussion" size="2rem" />
            <p>Select a channel to start chatting.</p>
            {channels.length === 0 && !loading && (
              <div className="vector-getting-started">
                <h4>Getting started</h4>
                <ol>
                  <li>
                    <Codicon name="robot" size="0.875rem" />
                    {' '}Register an agent — click the <Codicon name="add" size="0.75rem" /> "Add Agent" button in the sidebar
                  </li>
                  <li>
                    <Codicon name="comment-discussion" size="0.875rem" />
                    {' '}Create a channel — click the <Codicon name="new-file" size="0.75rem" /> "Create Channel" button
                  </li>
                  <li>
                    <Codicon name="mention" size="0.875rem" />
                    {' '}Select the channel and type <code>@handle</code> to mention an agent
                  </li>
                </ol>
                <div className="vector-quick-actions">
                  <button
                    className="vector-btn-primary"
                    onClick={() => $showAddAgent.set(true)}
                    type="button"
                  >
                    <Codicon name="add" size="0.75rem" /> Add Agent
                  </button>
                  <button
                    className="vector-btn-primary"
                    disabled={agents.length === 0}
                    onClick={() => $showCreateChannel.set(true)}
                    type="button"
                  >
                    <Codicon name="new-file" size="0.75rem" /> Create Channel
                  </button>
                </div>
                {agents.length === 0 && (
                  <p className="vector-hint">
                    Tip: Register an agent first — channels need at least one agent member to dispatch messages.
                  </p>
                )}
              </div>
            )}
          </div>
        )}
      </main>
      {showCreateChannel && <CreateChannelModal />}
      {showAddAgent && <AddAgentModal />}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Statusbar badge for total unread
// ---------------------------------------------------------------------------

function UnreadBadge() {
  const total = totalUnread()

  useEffect(() => {
    // No-op: live events not available in v0. Polling handles this.
  }, [])

  if (total === 0) {
    return null
  }

  return (
    <button
      className={cn(
        'inline-flex h-full items-center gap-1 rounded-none px-1.5 text-[0.6875rem] tabular-nums transition-colors',
        'text-(--ui-text-tertiary) hover:bg-(--chrome-action-hover) hover:text-foreground',
      )}
      onClick={() => host.navigate('/vector')}
      type="button"
    >
      <Codicon name="comment-discussion" size="0.7rem" />
      <span>{total}</span>
    </button>
  )
}

// ---------------------------------------------------------------------------
// Plugin registration
// ---------------------------------------------------------------------------

const plugin: HermesPlugin = {
  defaultEnabled: false,
  id: 'vector-channels',
  name: 'Vector Channels',
  register(ctx) {
    bindApi(ctx.rest as RestFn)

    ctx.registerMany([
      {
        data: { path: '/vector' } satisfies RouteContribution,
        id: 'page',
        area: ROUTES_AREA,
        render: () => <ChannelsPage />,
      },
      {
        data: {
          codicon: 'comment-discussion',
          label: 'Channels',
          path: '/vector',
        } satisfies SidebarNavContribution,
        id: 'nav',
        area: SIDEBAR_NAV_AREA,
        order: 60,
      },
      {
        id: 'unread',
        area: STATUSBAR_AREAS.right,
        order: 90,
        render: () => <UnreadBadge />,
      },
      {
        data: {
          id: 'vector.openChannels',
          keywords: ['vector', 'channels', 'agents', 'chat'],
          label: 'Vector: Open Channels',
          run: () => host.navigate('/vector'),
        } satisfies PaletteContribution,
        id: 'open',
        area: PALETTE_AREA,
      },
    ])
  },
}

export default plugin

// Export for testing
export {
  bindApi,
  type ChannelInfo,
  computeAutocomplete,
  incrementUnread,
  markRead,
  type MessageInfo,
  type RestFn,
  totalUnread,
}
