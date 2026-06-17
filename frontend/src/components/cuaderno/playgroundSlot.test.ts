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

import { launch, getState, close, idFromIframeUrl, _resetForTests } from './playgroundSlot'
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
const FALLBACK: FallbackResponse = { kind: 'fallback', reason: 'generator', iframe_url: '/playground/pg-42', playground_id: 'pg-42' }
const FALLBACK_WITH_REASON: FallbackResponse = { kind: 'fallback', reason: 'async function — nothing to step through', iframe_url: 'http://127.0.0.1:5000/', playground_id: 'pg-abc123' }
const req = { source: 'cuaderno' as const, function_ref: { file: 'a.py', name: 'f' }, breadcrumb: 'Step through f' }

beforeEach(() => {
  launchPlayground.mockReset()
  closePlayground.mockClear()
  vi.mocked(api.playgroundStatus).mockReset()
  _resetForTests()
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
      // playground_id taken directly from res.playground_id (not re-derived from iframe_url)
      expect(s.playgroundId).toBe('pg-42')
    }
  })

  it('uses res.playground_id directly (not idFromIframeUrl) for a "http://127.0.0.1:PORT/" fallback url', async () => {
    // The new contract: FallbackResponse carries playground_id; the frontend uses it directly.
    // idFromIframeUrl on 'http://127.0.0.1:5000/' would return '5000' (wrong!); playground_id='pg-abc123' is correct.
    launchPlayground.mockResolvedValue(FALLBACK_WITH_REASON)
    await launch('a.py:f:', req)
    const s = getState()
    expect(s.kind).toBe('live')
    if (s.kind === 'live') {
      expect(s.playgroundId).toBe('pg-abc123')   // direct from playground_id, NOT from idFromIframeUrl
      expect(s.fallbackReason).toBe('async function — nothing to step through')
    }
  })

  it('propagates res.reason as fallbackReason on the live slot', async () => {
    launchPlayground.mockResolvedValue(FALLBACK)
    await launch('a.py:f:', req)
    const s = getState()
    expect(s.kind).toBe('live')
    if (s.kind === 'live') {
      expect(s.fallbackReason).toBe('generator')
    }
  })

  it('treats kind:"trace" with empty trace as nothing_ran (not an empty Stepper)', async () => {
    const emptyTrace = { ...TRACE, trace: [] }
    launchPlayground.mockResolvedValue(emptyTrace)
    await launch('a.py:f:', req)
    const s = getState()
    expect(s.kind).toBe('nothing_ran')
    if (s.kind === 'nothing_ran') {
      expect(s.widgetKey).toBe('a.py:f:')
      expect(s.message).toMatch(/didn't run/)
    }
  })

  it('close() while in nothing_ran state transitions to ended', async () => {
    const emptyTrace = { ...TRACE, trace: [] }
    launchPlayground.mockResolvedValue(emptyTrace)
    await launch('a.py:f:', req)
    expect(getState().kind).toBe('nothing_ran')
    close()
    await Promise.resolve()
    expect(getState().kind).toBe('ended')
    const s = getState()
    if (s.kind === 'ended') {
      expect(s.reason).toBe('closed')
    }
  })

  it('a stale fallback closes orphaned playground via playground_id (not idFromIframeUrl)', async () => {
    let resolveFirst!: (v: FallbackResponse) => void
    launchPlayground.mockReturnValueOnce(new Promise((r) => { resolveFirst = r }))
    launchPlayground.mockResolvedValueOnce(TRACE)
    const p1 = launch('a.py:f:', req)
    await Promise.resolve()
    const p2 = launch('a.py:f:', req)
    await p2
    resolveFirst(FALLBACK_WITH_REASON)   // late fallback with explicit playground_id
    await p1
    // Must close 'pg-abc123', NOT '5000' (what idFromIframeUrl would return for the port-only url)
    expect(closePlayground).toHaveBeenCalledWith('pg-abc123')
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

  it('close() while in trace state transitions to ended (not a no-op)', async () => {
    launchPlayground.mockResolvedValue(TRACE)
    await launch('a.py:f:', req)
    expect(getState().kind).toBe('trace')
    close()
    // killCurrent is async but trace has no async work; flush micro-task queue
    await Promise.resolve()
    expect(getState().kind).toBe('ended')
    const s = getState()
    if (s.kind === 'ended') {
      expect(s.reason).toBe('closed')
      expect(s.widgetKey).toBe('a.py:f:')
    }
  })

  it('onActiveFrameChange() while in trace state transitions to ended (evicted)', async () => {
    const { onActiveFrameChange } = await import('./playgroundSlot')
    launchPlayground.mockResolvedValue(TRACE)
    await launch('a.py:f:', req)
    expect(getState().kind).toBe('trace')
    onActiveFrameChange()
    await Promise.resolve()
    expect(getState().kind).toBe('ended')
    const s = getState()
    if (s.kind === 'ended') {
      expect(s.reason).toBe('evicted')
    }
  })

  it('close() on an empty slot does NOT abort an in-flight launch via token race', async () => {
    // Bug: close() increments the global token even when slot.kind === 'empty'.
    // Sequence: launch() captures myToken = N, awaits killCurrent (no-op for
    // empty), yields — close() runs during the yield → token = N+1, launch()
    // resumes, sees token !== myToken, silently aborts. The launchPlayground API
    // call never fires and the slot stays empty (or stuck at spawning).
    //
    // Fix: close() is a no-op (returns early) when slot.kind === 'empty'.
    //
    // We reproduce by calling launch() then close() without any yield between
    // them so close() runs while launch() is suspended inside killCurrent.
    vi.resetModules()
    const s = await import('./playgroundSlot')
    const a = (await import('../../api/client')).api
    vi.mocked(a.launchPlayground).mockResolvedValue(TRACE)

    expect(s.getState().kind).toBe('empty')

    // launch() starts → myToken captured → enters killCurrent microtask.
    // close() fires immediately, BEFORE killCurrent's await resolves:
    const p = s.launch('a.py:f:', req)
    s.close()   // races with the killCurrent microtask
    await p
    await Promise.resolve()

    // With the bug: launch() aborts (token mismatch), launchPlayground never
    // called, slot stays empty → test would fail (kind !== 'trace').
    // With the fix: close() is a no-op on empty slot, launch() completes.
    expect(s.getState().kind).toBe('trace')
  })
})
