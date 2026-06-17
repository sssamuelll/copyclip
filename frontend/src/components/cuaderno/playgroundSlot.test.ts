import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'
import type { StepThroughResponse, FallbackResponse } from '../../types/api'

// vi.mock is hoisted — the factory must not reference top-level lets.
// Instead, expose the mocks through the module and grab them after import.
vi.mock('../../api/client', () => ({
  api: {
    launchPlayground: vi.fn(),
    closePlayground: vi.fn(() => Promise.resolve({ ok: true })),
    playgroundStatus: vi.fn(),
    playgroundList: vi.fn(() => Promise.resolve({ items: [] })),
  },
}))

import { launch, getState, close, idFromIframeUrl } from './playgroundSlot'
import { api } from '../../api/client'

const launchPlayground = vi.mocked(api.launchPlayground)
const closePlayground = vi.mocked(api.closePlayground)

const TRACE: StepThroughResponse = {
  kind: 'trace',
  trace: [{ line: 255, event: 'call', changed: ['x'], scope: [{ name: 'x', kind: 'scalar', text: '1' }] }],
  source_lines: [{ num: 255, text: 'def f(x):' }],
  func_name: 'f',
  file_line: 'a.py:255',
  truncated: false,
}
const FALLBACK: FallbackResponse = { kind: 'fallback', reason: 'generator', iframe_url: '/playground/pg-42' }
const req = { source: 'cuaderno' as const, function_ref: { file: 'a.py', name: 'f' }, breadcrumb: 'Step through f' }

beforeEach(() => {
  launchPlayground.mockReset()
  closePlayground.mockClear()
  vi.mocked(api.playgroundStatus).mockReset()
  close()
})
afterEach(() => { vi.useRealTimers() })

describe('idFromIframeUrl', () => {
  it('recovers the playground id from the last path segment', () => {
    expect(idFromIframeUrl('/playground/pg-42')).toBe('pg-42')
    expect(idFromIframeUrl('http://127.0.0.1:8000/playground/abc?token=x#frag')).toBe('abc')
    expect(idFromIframeUrl('/playground/abc/')).toBe('abc')
  })
})

describe('playgroundSlot', () => {
  it('lands in the trace slot on a kind:"trace" response and does not poll', async () => {
    launchPlayground.mockResolvedValue(TRACE)
    await launch('a.py:f:', req)
    const s = getState()
    expect(s.kind).toBe('trace')
    if (s.kind === 'trace') {
      expect(s.response.func_name).toBe('f')
      expect(s.widgetKey).toBe('a.py:f:')
    }
    expect(closePlayground).not.toHaveBeenCalled()
  })

  it('lands in the live slot on a kind:"fallback" response', async () => {
    launchPlayground.mockResolvedValue(FALLBACK)
    await launch('a.py:f:', req)
    const s = getState()
    expect(s.kind).toBe('live')
    if (s.kind === 'live') {
      expect(s.iframeUrl).toBe('/playground/pg-42')
      expect(s.playgroundId).toBe('pg-42')   // recovered via idFromIframeUrl
    }
  })

  it('a stale launch (superseded token) discards a late trace response', async () => {
    let resolveFirst!: (v: StepThroughResponse) => void
    launchPlayground.mockReturnValueOnce(new Promise((r) => { resolveFirst = r }))
    launchPlayground.mockResolvedValueOnce(TRACE)
    const p1 = launch('a.py:f:', req)   // token 1: pending at launchPlayground
    await Promise.resolve()              // yield so p1 reaches launchPlayground
    const p2 = launch('a.py:f:', req)   // token 2, resolves immediately
    await p2
    resolveFirst(TRACE)                  // token 1 resolves late
    await p1
    expect(getState().kind).toBe('trace') // token-2 result, not clobbered
  })

  it('a stale fallback closes the orphaned playground via the recovered id', async () => {
    let resolveFirst!: (v: FallbackResponse) => void
    launchPlayground.mockReturnValueOnce(new Promise((r) => { resolveFirst = r }))
    launchPlayground.mockResolvedValueOnce(TRACE)
    const p1 = launch('a.py:f:', req)
    await Promise.resolve()              // yield so p1 reaches launchPlayground
    const p2 = launch('a.py:f:', req)
    await p2
    resolveFirst(FALLBACK)               // late fallback for a dead token
    await p1
    expect(closePlayground).toHaveBeenCalledWith('pg-42')
  })
})
