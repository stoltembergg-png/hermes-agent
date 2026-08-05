/**
 * Vitest tests for vector-channels plugin — pure logic only.
 *
 * Tests the exported pure functions: computeAutocomplete, incrementUnread,
 * markRead, totalUnread.
 */

import { describe, it, expect, beforeEach } from 'vitest'
import {
  computeAutocomplete,
  incrementUnread,
  markRead,
  totalUnread,
  type ChannelInfo,
  type Message
} from './plugin'

describe('computeAutocomplete', () => {
  const members = ['gandalf', 'gandalf2', 'sre', 'devops', 'gandalf_clone']

  it('returns matching members for @gan prefix', () => {
    const result = computeAutocomplete('hello @gan', members)
    expect(result).toContain('gandalf')
    expect(result).toContain('gandalf2')
    expect(result).toContain('gandalf_clone')
  })

  it('returns exact match only when @sre is typed', () => {
    expect(computeAutocomplete('hi @sre', members)).toEqual(['sre'])
  })

  it('excludes the exact partial match itself', () => {
    // @gandalf should NOT return gandalf (it IS the partial)
    expect(computeAutocomplete('hi @gandalf', members)).not.toContain('gandalf')
    expect(computeAutocomplete('hi @gandalf', members)).toContain('gandalf2')
    expect(computeAutocomplete('hi @gandalf', members)).toContain('gandalf_clone')
  })

  it('returns empty for no @ mention', () => {
    expect(computeAutocomplete('hello world', members)).toEqual([])
  })

  it('returns empty for @ at end of text with no chars', () => {
    expect(computeAutocomplete('hello @', members)).toEqual([])
  })

  it('is case-insensitive', () => {
    expect(computeAutocomplete('@GAN', members)).toContain('gandalf')
  })

  it('returns all matching for @ga prefix', () => {
    const result = computeAutocomplete('@ga', members)
    expect(result.length).toBe(3)
  })

  it('works with a long message before the @', () => {
    const text = 'This is a long message that ends with @dev'
    expect(computeAutocomplete(text, members)).toEqual(['devops'])
  })

  it('returns empty array for @xnonexistent', () => {
    expect(computeAutocomplete('@xnonexistent', members)).toEqual([])
  })

  it('only matches at end of text (not in the middle)', () => {
    // @sre followed by more text should not autocomplete
    expect(computeAutocomplete('@sre hello there', members)).toEqual([])
  })
})

describe('unread badge logic', () => {
  beforeEach(() => {
    // Reset by marking all channels read
    markRead('ch1')
    markRead('ch2')
    markRead('ch3')
  })

  it('totalUnread starts at 0', () => {
    expect(totalUnread()).toBe(0)
  })

  it('incrementUnread adds 1', () => {
    incrementUnread('ch1')
    expect(totalUnread()).toBe(1)
    incrementUnread('ch1')
    expect(totalUnread()).toBe(2)
  })

  it('markRead clears a channel', () => {
    incrementUnread('ch1')
    incrementUnread('ch1')
    incrementUnread('ch2')
    expect(totalUnread()).toBe(3)
    markRead('ch1')
    expect(totalUnread()).toBe(1)
  })

  it('multiple channels tracked independently', () => {
    incrementUnread('ch1')
    incrementUnread('ch2')
    incrementUnread('ch3')
    incrementUnread('ch1')
    expect(totalUnread()).toBe(4)
    markRead('ch2')
    expect(totalUnread()).toBe(3)
  })

  it('marking a channel with no unread is a no-op', () => {
    markRead('nonexistent')
    expect(totalUnread()).toBe(0)
  })
})

describe('TypeShape', () => {
  it('ChannelInfo has id, name, member_count', () => {
    const ch: ChannelInfo = { id: '1', name: 'dev-room', member_count: 5 }
    expect(ch.id).toBe('1')
    expect(ch.name).toBe('dev-room')
    expect(ch.member_count).toBe(5)
  })

  it('Message has id, author_handle, body, created_at, mentions', () => {
    const msg: Message = {
      id: '1',
      author_handle: 'gandalf',
      body: 'hello',
      created_at: '2026-01-01T00:00:00Z',
      mentions: ['sre']
    }
    expect(msg.mentions).toEqual(['sre'])
  })
})
