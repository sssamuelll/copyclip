import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

// W4-4 / decision E: the analyze trigger must survive on a Wave-5 page. Settings
// survives, so it carries the trigger (DebtNavigatorPage, which had it, dies).
const calls: { startAnalyzeJob: any[][] } = { startAnalyzeJob: [] }
let analyzeResult: () => Promise<any> = () =>
  Promise.resolve({ ok: true, job_id: 'j1', already_running: false })
vi.mock('../api/client', () => ({
  api: {
    getConfig: () => Promise.resolve({}),
    setConfig: () => Promise.resolve({}),
    startAnalyzeJob: (...a: any[]) => {
      calls.startAnalyzeJob.push(a)
      return analyzeResult()
    },
  },
}))

import { SettingsPage } from './SettingsPage'

describe('SettingsPage analysis trigger', () => {
  beforeEach(() => {
    calls.startAnalyzeJob = []
    analyzeResult = () => Promise.resolve({ ok: true, job_id: 'j1', already_running: false })
  })

  it('starts a background analysis (non-blocking) and notifies', async () => {
    const notes: string[] = []
    render(<SettingsPage onNotify={(m) => notes.push(m)} />)
    const btn = await screen.findByRole('button', { name: /analyze/i })
    fireEvent.click(btn)
    expect(calls.startAnalyzeJob.length).toBe(1)
    await waitFor(() => expect(notes.some((m) => /background|started|análisis/i.test(m))).toBe(true))
  })

  it('says so when an analysis is already running', async () => {
    analyzeResult = () => Promise.resolve({ ok: true, job_id: 'j1', already_running: true })
    const notes: string[] = []
    render(<SettingsPage onNotify={(m) => notes.push(m)} />)
    fireEvent.click(await screen.findByRole('button', { name: /analyze/i }))
    await waitFor(() => expect(notes.some((m) => /already running|en curso/i.test(m))).toBe(true))
  })
})
