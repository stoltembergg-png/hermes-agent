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

// ---------------------------------------------------------------------------
// Provider/model catalog (PR-013) — mirrors GET /models in plugin_api.py,
// which in turn mirrors the dashboard /api/model/options picker payload.
// ---------------------------------------------------------------------------

/**
 * One provider row in the model catalog.
 *
 * `models` is the curated list of model IDs for that provider (the same
 * curated list the Hermes picker uses — NOT a raw /models dump).
 */
export interface ModelOptionProvider {
  slug: string
  name: string
  models: string[]
}

/**
 * Response of GET /models — the Hermes provider/model catalog.
 *
 * `model`/`provider` (top level) are the session's current selection, kept
 * for future UX (a "current" marker). The Add Agent modal only needs
 * `providers` to populate its dropdowns.
 */
export interface ModelOptionsResponse {
  providers: ModelOptionProvider[]
  model: string
  provider: string
}

export interface VectorApiError {
  error: {
    code: string
    message: string
    retryable: boolean
  }
}

// ---------------------------------------------------------------------------
// Error parsing — extract clean message from Vector API error envelope
// ---------------------------------------------------------------------------

/**
 * Parse an error thrown by the REST client into a human-readable string.
 * Handles Vector API error envelopes ({@link VectorApiError}), network
 * connection errors, and generic Error objects.
 */
export function parseApiError(e: unknown): string {
  if (e instanceof Error) {
    const raw = e.message

    // Try to extract Vector error envelope: "400: {"error":{"code":"...","message":"...",...}}"
    const match = raw.match(/^\d{3}:\s*(\{.*\})$/s)

    if (match) {
      try {
        const parsed = JSON.parse(match[1]) as VectorApiError

        if (parsed.error?.message) {
          let msg = parsed.error.message

          if (parsed.error.retryable === false) {
            msg += '\n\nThis action cannot be retried — try a different value.'
          }

          return msg
        }
      } catch {
        // JSON parse failed — fall through to raw message
      }
    }

    // Network / connection errors
    if (/failed to fetch|network|ECONNREFUSED|connect|ERR_CONNECTION/i.test(raw)) {
      return 'Cannot reach the Hermes backend. Is it running?'
    }

    return raw
  }

  return String(e)
}

// ---------------------------------------------------------------------------
// Client
// ---------------------------------------------------------------------------

type RestFn = <T>(path: string, opts?: { method?: string; body?: unknown }) => Promise<T>

export { type RestFn }
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
// Endpoints — relative paths (ctx.rest namespaces under /api/plugins/vector-channels/)
// ---------------------------------------------------------------------------

export async function getHealth(): Promise<HealthResponse> {
  return _call<HealthResponse>('/health')
}

/**
 * Fetch the Hermes provider/model catalog (PR-013).
 *
 * Delegates to GET /models in plugin_api.py, which calls the Hermes model
 * resolver (`build_model_options_payload`) — NOT the VectorService. The
 * returned providers + their curated model lists drive the Add Agent
 * modal's advanced provider/model dropdowns.
 */
export async function getModelOptions(): Promise<ModelOptionsResponse> {
  return _call<ModelOptionsResponse>('/models')
}

export async function listAgents(): Promise<AgentInfo[]> {
  const res = await _call<AgentListResponse>('/agents')

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
  return _call<AgentInfo>('/agents', { method: 'POST', body: req })
}

export async function listChannels(): Promise<ChannelInfo[]> {
  const res = await _call<ChannelListResponse>('/channels')

  return res.channels
}

export async function createChannel(name: string, members: string[]): Promise<ChannelInfo> {
  return _call<ChannelInfo>('/channels', {
    method: 'POST',
    body: { name, members } as CreateChannelRequest
  })
}

export async function getMembers(channelId: string): Promise<string[]> {
  const res = await _call<MemberListResponse>(`/channels/${channelId}/members`)

  return res.members
}

export async function getHistory(channelId: string, limit = 50): Promise<MessageInfo[]> {
  const res = await _call<HistoryResponse>(`/channels/${channelId}/messages?limit=${limit}`)

  return res.messages
}

export async function deleteAgent(handle: string): Promise<void> {
  await _call<{ ok: boolean }>(`/agents/${encodeURIComponent(handle)}`, { method: 'DELETE' })
}

export async function postMessage(
  channelId: string,
  authorHandle: string,
  body: string,
  dispatch = true
): Promise<PostMessageResponse> {
  return _call<PostMessageResponse>(`/channels/${channelId}/messages`, {
    method: 'POST',
    body: {
      author_handle: authorHandle,
      body,
      dispatch
    } as PostMessageRequest
  })
}
