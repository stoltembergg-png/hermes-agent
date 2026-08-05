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
import { type ChangeEvent, type KeyboardEvent, useEffect } from 'react'

import {
  postMessage as apiPostMessage,
  bindApi,
  type ChannelInfo,
  getHistory,
  getMembers,
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
const $composer = atom('')
const $autocomplete = atom<string[]>([])
const $loading = atom(false)

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

async function postAndDispatch(channelId: string, body: string): Promise<void> {
  $loading.set(true)
  try {
    const result = await apiPostMessage(channelId, 'human', body, true)
    // The response includes the user message AND agent responses.
    // Render all returned messages immediately — no polling needed.
    const allMsgs = result.messages
    if (allMsgs.length > 0) {
      $messages.set(allMsgs)
    } else {
      // Fallback: at least show the user message
      const msgs = $messages.get()
      $messages.set([...msgs, result.message])
    }
  } catch {
    // Error state — non-fatal, preserves existing messages
  } finally {
    $loading.set(false)
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

function ChannelsPage() {
  const channels = useValue($channels)
  const messages = useValue($messages)
  const activeChannel = useValue($activeChannel)
  const loading = useValue($loading)

  useEffect(() => {
    void listChannels().then(chs => $channels.set(chs))
  }, [])

  return (
    <div className="vector-page" data-testid="vector-nav">
      <aside className="vector-sidebar" data-testid="vector-channel-list">
        <h2 className="sidebar-title">Channels</h2>
        {channels.map(ch => (
          <ChannelRow channel={ch} key={ch.id} />
        ))}
        {channels.length === 0 && (
          <p className="text-(--ui-text-tertiary) text-xs px-3 py-2">No channels.</p>
        )}
      </aside>
      <main className="vector-main">
        {activeChannel ? (
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
          </div>
        )}
      </main>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Statusbar badge for total unread
// ---------------------------------------------------------------------------

function UnreadBadge() {
  const channels = useValue($channels)
  const unread = useValue($unread)
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
  id: 'vector-channels',
  name: 'Vector Channels',
  defaultEnabled: false,
  register(ctx) {
    // Bind the REST door. api.ts calls /api/vector/* endpoints.
    bindApi(ctx.rest as RestFn)

    ctx.registerMany([
      {
        id: 'page',
        area: ROUTES_AREA,
        data: { path: '/vector' } satisfies RouteContribution,
        render: () => <ChannelsPage />,
      },
      {
        id: 'nav',
        area: SIDEBAR_NAV_AREA,
        order: 60,
        data: {
          codicon: 'comment-discussion',
          label: 'Channels',
          path: '/vector',
        } satisfies SidebarNavContribution,
      },
      {
        id: 'unread',
        area: STATUSBAR_AREAS.right,
        order: 90,
        render: () => <UnreadBadge />,
      },
      {
        id: 'open',
        area: PALETTE_AREA,
        data: {
          id: 'vector.openChannels',
          label: 'Vector: Open Channels',
          keywords: ['vector', 'channels', 'agents', 'chat'],
          run: () => host.navigate('/vector'),
        } satisfies PaletteContribution,
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
