import { api } from '../../api/client'
import type { PlaygroundLaunchRequest, StepThroughResponse } from '../../types/api'

export type SlotState =
  | { kind: 'empty' }
  | { kind: 'spawning'; widgetKey: string; token: number }
  | { kind: 'live'; widgetKey: string; playgroundId: string; iframeUrl: string; fallbackReason?: string; token: number }
  | { kind: 'trace'; widgetKey: string; response: StepThroughResponse; token: number }
  | { kind: 'ended'; widgetKey: string; reason: 'closed' | 'evicted' | 'exited' | 'error'; message?: string }
  | { kind: 'nothing_ran'; widgetKey: string; message: string; token: number }

let state: SlotState = { kind: 'empty' }
let token = 0
let pollTimer: ReturnType<typeof setInterval> | null = null
const listeners = new Set<() => void>()

function set(next: SlotState) { state = next; listeners.forEach((l) => l()) }
export function subscribe(l: () => void): () => void { listeners.add(l); return () => { listeners.delete(l) } }
export function getState(): SlotState { return state }
/** Expose the current launch token for ownership guards in UI components. */
export function getToken(): number { return token }

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
  } else if (state.kind === 'trace') {
    // capture-only: no subprocess to close, but the slot must transition to
    // ended so subscribers (e.g. PlaygroundWidget) reflect the new state.
    set({ kind: 'ended', widgetKey: state.widgetKey, reason })
  } else if (state.kind === 'nothing_ran') {
    set({ kind: 'ended', widgetKey: state.widgetKey, reason })
  } else if (state.kind === 'ended') {
    // × on an EndedCard: dismiss the card by returning the slot to 'empty',
    // so Widget B can start a fresh playground (the guard at PlaygroundWidget
    // line 121 checks slot.kind !== 'ended' before allowing a new launch).
    set({ kind: 'empty' })
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
      if (res.kind === 'fallback') {
        const id = res.playground_id ?? idFromIframeUrl(res.iframe_url)
        api.closePlayground(id).catch(() => {})
      }
      return
    }
    if (res.kind === 'trace') {
      if (res.trace.length === 0) {
        // Empty trace: the user's call did not enter the target function.
        // Use the server-provided func_name as the authoritative name — single source.
        // Treat as 'nothing ran' rather than mounting an empty Stepper.
        const nrMsg = res.func_name
          ? `${res.func_name}: call did not enter this function`
          : 'call did not enter the target function'
        set({ kind: 'nothing_ran', widgetKey, message: nrMsg, token: myToken })
        return
      }
      // capture-only: no subprocess to poll, the trace is immutable per launch
      set({ kind: 'trace', widgetKey, response: res, token: myToken })
    } else if (res.kind === 'fallback') {
      // Use playground_id directly; fall back to idFromIframeUrl only if absent (older server)
      const playgroundId = res.playground_id ?? idFromIframeUrl(res.iframe_url)
      set({ kind: 'live', widgetKey, playgroundId, iframeUrl: res.iframe_url, fallbackReason: res.reason, token: myToken })
      startPoll(playgroundId, widgetKey, myToken)
    } else {
      // Non-cuaderno PlaygroundLaunchResponse (no kind field): treat as live iframe
      const { playground_id, iframe_url } = res as unknown as { playground_id: string; iframe_url: string }
      const playgroundId = playground_id ?? idFromIframeUrl(iframe_url)
      set({ kind: 'live', widgetKey, playgroundId, iframeUrl: iframe_url, token: myToken })
      startPoll(playgroundId, widgetKey, myToken)
    }
  } catch (e) {
    if (token !== myToken) return
    set({ kind: 'ended', widgetKey, reason: 'error', message: e instanceof Error ? e.message : String(e) })
  }
}

export function close(): void {
  // Guard: if nothing is active, don't touch the token. An idle widget's ×
  // should never increment the global token — doing so would race with any
  // concurrent in-flight launch() that has already passed the killCurrent
  // await (myToken would no longer equal token → silent abort).
  if (state.kind === 'empty') return
  token++; void killCurrent('closed')
}

/** Navigation = death (one-frame reality): any active-frame change kills the runtime. */
export function onActiveFrameChange(): void { token++; void killCurrent('evicted') }

/** Mount reconciliation: anything alive at mount is an orphan from a previous load. */
export async function reconcileOnMount(): Promise<void> {
  try {
    const res = await api.playgroundList()
    await Promise.all(res.items.map((i) => api.closePlayground(i.id).catch(() => {})))
  } catch { /* list route unavailable: nothing to do */ }
}

/**
 * Hard-reset the slot to empty — for use in test beforeEach only.
 * Stops any active poll and resets state + token without calling the API.
 * NOT intended for production code paths.
 */
export function _resetForTests(): void {
  stopPoll()
  token = 0
  state = { kind: 'empty' }
  listeners.forEach((l) => l())
}
