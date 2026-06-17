import { api } from '../../api/client'
import type { PlaygroundLaunchRequest, StepThroughResponse } from '../../types/api'

export type SlotState =
  | { kind: 'empty' }
  | { kind: 'spawning'; widgetKey: string; token: number }
  | { kind: 'live'; widgetKey: string; playgroundId: string; iframeUrl: string; token: number }
  | { kind: 'trace'; widgetKey: string; response: StepThroughResponse; token: number }
  | { kind: 'ended'; widgetKey: string; reason: 'closed' | 'evicted' | 'exited' | 'error'; message?: string }

let state: SlotState = { kind: 'empty' }
let token = 0
let pollTimer: ReturnType<typeof setInterval> | null = null
const listeners = new Set<() => void>()

function set(next: SlotState) { state = next; listeners.forEach((l) => l()) }
export function subscribe(l: () => void): () => void { listeners.add(l); return () => { listeners.delete(l) } }
export function getState(): SlotState { return state }

/** Recover the playground id from a fallback iframe_url ("/playground/<id>"). */
export function idFromIframeUrl(url: string): string {
  // Strip query string and fragment, then take the last non-empty path segment.
  const path = url.split('?')[0].split('#')[0]
  const parts = path.split('/').filter(Boolean)
  return parts[parts.length - 1] ?? url
}

function stopPoll() { if (pollTimer) { clearInterval(pollTimer); pollTimer = null } }

function startPoll(id: string, widgetKey: string, myToken: number) {
  stopPoll()
  pollTimer = setInterval(async () => {
    try {
      const s = await api.playgroundStatus(id)
      if (token !== myToken) return
      if (s.status !== 'running') {
        stopPoll()
        api.closePlayground(id).catch(() => {})
        set({ kind: 'ended', widgetKey, reason: 'exited' })
      }
    } catch { /* network blip: keep polling */ }
  }, 5000)
}

async function killCurrent(reason: 'closed' | 'evicted'): Promise<void> {
  stopPoll()
  if (state.kind === 'live') {
    const { playgroundId, widgetKey } = state
    set({ kind: 'ended', widgetKey, reason })
    try { await api.closePlayground(playgroundId) } catch { /* reaped on next reconcile */ }
  } else if (state.kind === 'spawning') {
    set({ kind: 'ended', widgetKey: state.widgetKey, reason })
  }
}

export async function launch(widgetKey: string, req: PlaygroundLaunchRequest): Promise<void> {
  const myToken = ++token              // absorbs double-clicks: stale awaits no-op
  await killCurrent('evicted')          // awaited DELETE BEFORE the new POST
  if (token !== myToken) return
  set({ kind: 'spawning', widgetKey, token: myToken })
  try {
    const res = await api.launchPlayground(req)
    if (token !== myToken) {
      // late result for a superseded launch: a fallback spawned a real
      // playground we must reap; a trace has no subprocess.
      if (res.kind === 'fallback') api.closePlayground(idFromIframeUrl(res.iframe_url)).catch(() => {})
      return
    }
    if (res.kind === 'trace') {
      // capture-only: no subprocess to poll, the trace is immutable per launch
      set({ kind: 'trace', widgetKey, response: res, token: myToken })
    } else {
      const playgroundId = idFromIframeUrl(res.iframe_url)
      set({ kind: 'live', widgetKey, playgroundId, iframeUrl: res.iframe_url, token: myToken })
      startPoll(playgroundId, widgetKey, myToken)
    }
  } catch (e) {
    if (token !== myToken) return
    set({ kind: 'ended', widgetKey, reason: 'error', message: e instanceof Error ? e.message : String(e) })
  }
}

export function close(): void { token++; void killCurrent('closed') }

/** Navigation = death (one-frame reality): any active-frame change kills the runtime. */
export function onActiveFrameChange(): void { token++; void killCurrent('evicted') }

/** Mount reconciliation: anything alive at mount is an orphan from a previous load. */
export async function reconcileOnMount(): Promise<void> {
  try {
    const res = await api.playgroundList()
    await Promise.all(res.items.map((i) => api.closePlayground(i.id).catch(() => {})))
  } catch { /* list route unavailable: nothing to do */ }
}
