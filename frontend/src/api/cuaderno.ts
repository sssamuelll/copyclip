import type { CuadernoSession, CuadernoStreamEvent, CuadernoProvidersResponse, EntryCueResponse } from '../types/api'

async function patchJson<T>(url: string, body: unknown): Promise<T> {
  const r = await fetch(url, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!r.ok) {
    const text = await r.text()
    throw new Error(`PATCH ${url} → ${r.status}: ${text}`)
  }
  return (await r.json()) as T
}

async function getJson<T>(url: string): Promise<T> {
  const r = await fetch(url)
  if (!r.ok) {
    const text = await r.text()
    throw new Error(`GET ${url} → ${r.status}: ${text}`)
  }
  return (await r.json()) as T
}

async function postJson<T>(url: string, body: unknown): Promise<T> {
  const r = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!r.ok) {
    const text = await r.text()
    throw new Error(`POST ${url} → ${r.status}: ${text}`)
  }
  return (await r.json()) as T
}

export const cuadernoApi = {
  session(sessionId: string) {
    return getJson<CuadernoSession>(
      `/api/cuaderno/sessions/${encodeURIComponent(sessionId)}`,
    )
  },
  patchQuestion(
    sessionId: string,
    position: number,
    fields: { bookmarked?: boolean; answer_check?: 'answers' | 'not_yet' | null },
  ) {
    return patchJson<{ ok: boolean }>(
      `/api/cuaderno/sessions/${encodeURIComponent(sessionId)}/questions/${position}`,
      fields,
    )
  },
  providers() {
    return getJson<CuadernoProvidersResponse>('/api/cuaderno/providers')
  },
  entryCue() {
    return getJson<EntryCueResponse>('/api/cuaderno/entry-cue')
  },
  setProvider(provider: string, model: string) {
    return postJson<{ status: string }>('/api/config', {
      cuaderno_provider: provider,
      cuaderno_model: model,
    })
  },
}

// Streams POST /api/cuaderno/ask as text/event-stream. EventSource cannot be
// used because it is GET-only and this endpoint needs a JSON POST body, so we
// read the response body with fetch + a ReadableStream reader and parse SSE
// records ("data: <json>\n\n") ourselves, buffering across chunk boundaries.
export async function askStream(
  question: string,
  sessionId: string | undefined,
  opts: { onEvent: (e: CuadernoStreamEvent) => void; signal?: AbortSignal },
): Promise<void> {
  const r = await fetch('/api/cuaderno/ask', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, session_id: sessionId }),
    signal: opts.signal,
  })
  if (!r.ok || !r.body) {
    const text = r.body ? await r.text() : ''
    throw new Error(`POST /api/cuaderno/ask → ${r.status}: ${text}`)
  }
  const reader = r.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    let sep
    while ((sep = buf.indexOf('\n\n')) !== -1) {
      const record = buf.slice(0, sep)
      buf = buf.slice(sep + 2)
      const dataLine = record
        .split('\n')
        .find((l) => l.startsWith('data:'))
      if (!dataLine) continue
      const json = dataLine.slice(5).trim()
      if (!json) continue
      opts.onEvent(JSON.parse(json) as CuadernoStreamEvent)
    }
  }
}
