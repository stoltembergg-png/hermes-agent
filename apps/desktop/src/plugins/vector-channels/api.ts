/**
 * Typed Vector API client.
 *
 * All REST calls to the Vector gateway live here so plugin.tsx
 * stays focused on rendering and state.
 */

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface AgentInfo {
  handle: string
  description: string | null
  model: string | null
  provider: string | null
  tools: string[]
}

export interface AgentListResponse {
  agents: AgentInfo[]
}

export interface ChannelInfo {
  id: string
  name: string
  member_count?: number
}

export interface ChannelListResponse {
  channels: ChannelInfo[]
}

export interface CreateChannelRequest {
  name: string
  members: string[]
}

export interface MessageInfo {
  id: string
  channel_id: string
  author_handle: string
  body: string
  mentions: string[]
  created_at: string
}

export interface HistoryResponse {
  messages: MessageInfo[]
}

export interface MemberListResponse {
  members: string[]
}

export interface PostMessageRequest {
  author_handle: string
  body: string
  dispatch?: boolean
}

export interface DispatchEntry {
  handle: string
  depth: number
  status: string
  response: string
}

export interface DispatchResult {
  entries: DispatchEntry[]
  recursion_exceeded: boolean
  error: string | null
}

export interface PostMessageResponse {
  message: MessageInfo
  dispatch: DispatchResult | null
  messages: MessageInfo[]
}

export interface HealthResponse {
  status: string
  version: string
  storage: string
}

export interface VectorApiError {
  error: {
    code: string
    message: string
    retryable: boolean
  }
}

// ---------------------------------------------------------------------------
// Client
// ---------------------------------------------------------------------------

type RestFn = <T>(path: string, opts?: { method?: string; body?: unknown }) => Promise<T>

let _rest: RestFn | null = null

export function bindApi(rest: RestFn): void {
  _rest = rest
}

function _call<T>(path: string, opts?: { method?: string; body?: unknown }): Promise<T> {
  if (!_rest) {
    return Promise.reject(new Error('Vector API client not initialized'))
  }
  return _rest<T>(path, opts)
}

// ---------------------------------------------------------------------------
// Endpoints — all prefixed with /api/vector
// ---------------------------------------------------------------------------

export async function getHealth(): Promise<HealthResponse> {
  return _call<HealthResponse>('/api/vector/health')
}

export async function listAgents(): Promise<AgentInfo[]> {
  const res = await _call<AgentListResponse>('/api/vector/agents')
  return res.agents
}

export async function createAgent(req: {
  handle: string
  system_prompt: string
  description?: string
  model?: string
  provider?: string
  tools?: string[]
  fallback_models?: string[]
}): Promise<AgentInfo> {
  return _call<AgentInfo>('/api/vector/agents', { method: 'POST', body: req })
}

export async function listChannels(): Promise<ChannelInfo[]> {
  const res = await _call<ChannelListResponse>('/api/vector/channels')
  return res.channels
}

export async function createChannel(name: string, members: string[]): Promise<ChannelInfo> {
  return _call<ChannelInfo>('/api/vector/channels', {
    method: 'POST',
    body: { name, members } as CreateChannelRequest,
  })
}

export async function getMembers(channelId: string): Promise<string[]> {
  const res = await _call<MemberListResponse>(`/api/vector/channels/${channelId}/members`)
  return res.members
}

export async function getHistory(channelId: string, limit = 50): Promise<MessageInfo[]> {
  const res = await _call<HistoryResponse>(`/api/vector/channels/${channelId}/messages?limit=${limit}`)
  return res.messages
}

export async function postMessage(
  channelId: string,
  authorHandle: string,
  body: string,
  dispatch = true,
): Promise<PostMessageResponse> {
  return _call<PostMessageResponse>(`/api/vector/channels/${channelId}/messages`, {
    method: 'POST',
    body: {
      author_handle: authorHandle,
      body,
      dispatch,
    } as PostMessageRequest,
  })
}
