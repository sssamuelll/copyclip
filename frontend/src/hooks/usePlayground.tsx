import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { api } from '../api/client'
import type { PlaygroundLaunchRequest, PlaygroundLaunchResponse } from '../types/api'

export type PlaygroundErrorInfo = {
  code: string
  message: string
  install_hint?: string
}

export type PlaygroundState =
  | { kind: 'idle' }
  | { kind: 'loading'; req: PlaygroundLaunchRequest }
  | { kind: 'ready'; req: PlaygroundLaunchRequest; res: PlaygroundLaunchResponse }
  | { kind: 'error'; req: PlaygroundLaunchRequest; error: PlaygroundErrorInfo }

type PlaygroundContextValue = {
  state: PlaygroundState
  launch: (req: PlaygroundLaunchRequest) => Promise<void>
  close: () => Promise<void>
}

const PlaygroundContext = createContext<PlaygroundContextValue | null>(null)

// The api client wraps backend errors in Error objects with .payload and
// .status attached (see toAPIError in api/client.ts). Backend playground
// error payloads have the shape { error, message, install_hint? }. We
// normalize into a flat PlaygroundErrorInfo so the panel can render error
// states off a stable code field.
function extractError(e: unknown): PlaygroundErrorInfo {
  if (e && typeof e === 'object' && 'payload' in e) {
    const payload = (e as { payload?: unknown }).payload
    if (payload && typeof payload === 'object') {
      const p = payload as Record<string, unknown>
      const code = typeof p.error === 'string' ? p.error : 'unknown_error'
      const message =
        typeof p.message === 'string' && p.message
          ? p.message
          : typeof p.error === 'string'
            ? p.error
            : 'Unknown error'
      const install_hint = typeof p.install_hint === 'string' ? p.install_hint : undefined
      return { code, message, install_hint }
    }
  }
  return {
    code: 'unknown_error',
    message: e instanceof Error ? e.message : String(e),
  }
}

export function PlaygroundProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<PlaygroundState>({ kind: 'idle' })
  // Mirror state into a ref so `close` can read the latest playground id
  // without invalidating the callback on every state transition.
  const stateRef = useRef(state)
  stateRef.current = state
  // Monotonic token bumped on every launch/close. The in-flight POST
  // checks the token before committing state; if the user closed or
  // launched a fresh playground while the spawn was running, the stale
  // response is silently torn down so we never end up with a registered
  // playground the user never saw.
  const launchTokenRef = useRef(0)

  const close = useCallback(async () => {
    const current = stateRef.current
    launchTokenRef.current += 1
    setState({ kind: 'idle' })
    if (current.kind === 'ready') {
      try {
        await api.closePlayground(current.res.playground_id)
      } catch {
        // best-effort: orphan playgrounds are reaped on next restart
      }
    }
  }, [])

  const launch = useCallback(async (req: PlaygroundLaunchRequest) => {
    const token = ++launchTokenRef.current
    setState({ kind: 'loading', req })
    try {
      const res = await api.launchPlayground(req)
      if (launchTokenRef.current === token) {
        setState({ kind: 'ready', req, res })
      } else {
        // User closed (or re-launched) while we were waiting for the
        // spawn. Tear down the orphan immediately rather than leaking it
        // until the next CopyClip restart.
        api.closePlayground(res.playground_id).catch(() => {})
      }
    } catch (e) {
      if (launchTokenRef.current === token) {
        setState({ kind: 'error', req, error: extractError(e) })
      }
    }
  }, [])

  const value = useMemo<PlaygroundContextValue>(
    () => ({ state, launch, close }),
    [state, launch, close],
  )

  // Expose a tiny debug handle on window so devtools can drive the panel
  // through its four states without needing a live surface connector. Kept
  // unconditionally because CopyClip is a local-only dashboard — there's no
  // production surface to leak to.
  useEffect(() => {
    if (typeof window === 'undefined') return
    const w = window as unknown as {
      __playground?: { launch: typeof launch; close: typeof close; state: () => PlaygroundState }
    }
    w.__playground = { launch, close, state: () => stateRef.current }
    return () => {
      delete w.__playground
    }
  }, [launch, close])

  return <PlaygroundContext.Provider value={value}>{children}</PlaygroundContext.Provider>
}

export function usePlayground(): PlaygroundContextValue {
  const ctx = useContext(PlaygroundContext)
  if (!ctx) {
    throw new Error('usePlayground must be called inside <PlaygroundProvider>')
  }
  return ctx
}
