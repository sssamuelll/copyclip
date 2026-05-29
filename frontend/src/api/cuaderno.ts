import type { CuadernoAskResponse, CuadernoSession } from '../types/api'

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

export const cuadernoApi = {
  ask(question: string, sessionId?: string) {
    return postJson<CuadernoAskResponse>('/api/cuaderno/ask', {
      question,
      session_id: sessionId,
    })
  },
  session(sessionId: string) {
    return getJson<CuadernoSession>(
      `/api/cuaderno/sessions/${encodeURIComponent(sessionId)}`,
    )
  },
  patchQuestion(
    sessionId: string,
    position: number,
    fields: { bookmarked?: boolean; got_it?: 'got' | 'didnt' | null },
  ) {
    return patchJson<{ ok: boolean }>(
      `/api/cuaderno/sessions/${encodeURIComponent(sessionId)}/questions/${position}`,
      fields,
    )
  },
}
