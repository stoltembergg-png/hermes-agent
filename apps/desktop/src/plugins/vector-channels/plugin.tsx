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
import { type ChangeEvent, type KeyboardEvent, useEffect, useState } from 'react'

import {
  postMessage as apiPostMessage,
  bindApi,
  type ChannelInfo,
  createAgent,
  createChannel,
  getHealth,
  getHistory,
  getMembers,
  listAgents,
  listChannels,
  type MessageInfo,
  type RestFn,
} from './api'

// ---------------------------------------------------------------------------
// State atoms (plugin-local nanostores)
// ---------------------------------------------------------------------------

const $channels = atom<ChannelInfo[]>([])
const $activeChannel = atom<string | null>(null)
const $messages = atom<MessageInfo[]>([])
const $unread = atom<Record<string, number>>({})
const $members = atom<string[]>([])
const $agents = atom<string[]>([])
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
      setErr(e instanceof Error ? e.message : 'Failed to create channel')
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

  const handleCreate = async () => {
    if (!handle.trim() || !prompt.trim()) {
      return
    }

    setCreating(true)
    setErr(null)

    try {
      await createAgent({
        handle: handle.trim(),
        system_prompt: prompt.trim(),
      })
      // Refresh agents
      const agentList = await listAgents()
      $agents.set(agentList.map(a => a.handle))
      $showAddAgent.set(false)
      setHandle('')
      setPrompt('')
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Failed to create agent')
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
    $agents.set(agentList.map(a => a.handle))
  } catch {
    // Non-fatal
  }
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
  } finally {
    $loading.set(false)
  }
}

async function postAndDispatch(channelId: string, body: string): Promise<void> {
  $loading.set(true)

  try {
    const result = await apiPostMessage(channelId, 'human', body, true)
    const allMsgs = result.messages

    if (allMsgs.length > 0) {
      $messages.set(allMsgs)
    } else {
      const msgs = $messages.get()
      $messages.set([...msgs, result.message])
    }
  } catch {
    // Error state — non-fatal, preserves existing messages
  } finally {
    $loading.set(false)
  }
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

  useEffect(() => {
    void (async () => {
      $loading.set(true)
      $error.set(null)

      try {
        // Check if the vector API is reachable
        await getHealth()
        const [chs, agentList] = await Promise.all([listChannels(), listAgents()])
        $channels.set(chs)
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
        ) : activeChannel ? (
          <>
            <div className="message-list" data-testid="vector-message-list">
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
