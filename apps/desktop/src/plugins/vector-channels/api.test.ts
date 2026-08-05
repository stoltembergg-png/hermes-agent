/**
 * Vitest tests for the Vector typed API client.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  bindApi,
  createChannel,
  getHealth,
  getHistory,
  getMembers,
  listAgents,
  listChannels,
  postMessage,
  type RestFn,
} from './api'

// ---------------------------------------------------------------------------
// Mock REST function
// ---------------------------------------------------------------------------

function makeMockRest(): RestFn {
  return vi.fn(<T>(path: string, opts?: { method?: string; body?: unknown }): Promise<T> => {
    if (path.endsWith('/health')) {
      return Promise.resolve({ status: 'ok', version: '0.1.0', storage: 'sqlite' } as T)
    }
    if (path === '/api/vector/agents') {
      if (opts?.method === 'POST') {
        return Promise.resolve({
          handle: 'gandalf',
          description: null,
          model: null,
          provider: null,
          tools: [],
        } as T)
      }
      return Promise.resolve({
        agents: [
          { handle: 'gandalf', description: null, model: null, provider: null, tools: [] },
        ],
      } as T)
    }
    if (path === '/api/vector/channels') {
      if (opts?.method === 'POST') {
        return Promise.resolve({ id: 'ch1', name: 'dev' } as T)
      }
      return Promise.resolve({
        channels: [{ id: 'ch1', name: 'dev', member_count: 2 }],
      } as T)
    }
    if (path.includes('/members')) {
      return Promise.resolve({ members: ['human', 'gandalf'] } as T)
    }
    if (path.includes('/messages') && opts?.method !== 'POST') {
      return Promise.resolve({
        messages: [
          {
            id: 'm1',
            channel_id: 'ch1',
            author_handle: 'human',
            body: '@gandalf hello',
            mentions: ['gandalf'],
            created_at: '2026-01-01T00:00:00Z',
          },
        ],
      } as T)
    }
    if (path.includes('/messages') && opts?.method === 'POST') {
      return Promise.resolve({
        message: {
          id: 'm1',
          channel_id: 'ch1',
          author_handle: 'human',
          body: '@gandalf hello',
          mentions: ['gandalf'],
          created_at: '2026-01-01T00:00:00Z',
        },
        dispatch: {
          entries: [
            { handle: 'gandalf', depth: 0, status: 'ok', response: 'The architecture is sound.' },
          ],
          recursion_exceeded: false,
          error: null,
        },
        messages: [
          {
            id: 'm1',
            channel_id: 'ch1',
            author_handle: 'human',
            body: '@gandalf hello',
            mentions: ['gandalf'],
            created_at: '2026-01-01T00:00:00Z',
          },
          {
            id: 'm2',
            channel_id: 'ch1',
            author_handle: 'gandalf',
            body: 'The architecture is sound.',
            mentions: [],
            created_at: '2026-01-01T00:01:00Z',
          },
        ],
      } as T)
    }
    return Promise.resolve({} as T)
  }) as RestFn
}

// ---------------------------------------------------------------------------

describe('Vector API client', () => {
  beforeEach(() => {
    bindApi(makeMockRest())
  })

  it('getHealth calls /api/vector/health', async () => {
    const h = await getHealth()
    expect(h.status).toBe('ok')
    expect(h.storage).toBe('sqlite')
  })

  it('listAgents returns AgentInfo[]', async () => {
    const agents = await listAgents()
    expect(agents.length).toBe(1)
    expect(agents[0].handle).toBe('gandalf')
  })

  it('listChannels returns ChannelInfo[]', async () => {
    const channels = await listChannels()
    expect(channels.length).toBe(1)
    expect(channels[0].id).toBe('ch1')
    expect(channels[0].name).toBe('dev')
  })

  it('createChannel sends POST with name and members', async () => {
    const ch = await createChannel('dev', ['human', 'gandalf'])
    expect(ch.id).toBe('ch1')
    expect(ch.name).toBe('dev')
  })

  it('getMembers returns string[]', async () => {
    const members = await getMembers('ch1')
    expect(members).toContain('human')
    expect(members).toContain('gandalf')
  })

  it('getHistory returns MessageInfo[]', async () => {
    const history = await getHistory('ch1', 50)
    expect(history.length).toBe(1)
    expect(history[0].body).toBe('@gandalf hello')
  })

  it('postMessage returns PostMessageResponse with dispatch + messages', async () => {
    const result = await postMessage('ch1', 'human', '@gandalf hello', true)
    expect(result.message.author_handle).toBe('human')
    expect(result.dispatch).not.toBeNull()
    expect(result.dispatch!.entries.length).toBe(1)
    expect(result.dispatch!.entries[0].handle).toBe('gandalf')
    expect(result.messages.length).toBe(2)
    expect(result.messages[1].author_handle).toBe('gandalf')
  })
})
