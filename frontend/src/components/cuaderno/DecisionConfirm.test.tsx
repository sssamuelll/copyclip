import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

// Closure mock (not vi.fn): the component creates/consumes the result promise
// directly, so a rejected result is handled by the component's await — no vi.fn
// settledResults tracking to falsely flag it as unhandled.
const calls: any[][] = []
let result: () => Promise<any> = () => Promise.resolve({ ok: true })
vi.mock('../../api/client', () => ({
  api: { updateDecisionStatus: (...a: any[]) => { calls.push(a); return result() } },
}))

import { DecisionConfirm } from './DecisionConfirm'

describe('DecisionConfirm', () => {
  beforeEach(() => {
    calls.length = 0
    result = () => Promise.resolve({ ok: true })
  })

  it('PATCHes the decision only on the human click, then shows it applied', async () => {
    result = () => Promise.resolve({ ok: true, id: 3, status: 'accepted' })
    render(<DecisionConfirm action={{ decision_id: 3, to_status: 'accepted' }} />)
    expect(calls.length).toBe(0) // nothing is written until the human clicks
    fireEvent.click(screen.getByRole('button'))
    expect(calls[0]).toEqual([3, 'accepted'])
    // once applied, the button is gone (no re-confirm) and a confirmation shows
    await waitFor(() => expect(screen.queryByRole('button')).toBeNull())
    expect(screen.getByText(/✓/)).toBeTruthy()
  })

  it('surfaces a backend rejection without claiming success', async () => {
    result = () => Promise.reject(new Error('quality_gate_blocked'))
    render(<DecisionConfirm action={{ decision_id: 5, to_status: 'resolved' }} />)
    fireEvent.click(screen.getByRole('button'))
    expect(await screen.findByText(/quality_gate_blocked/)).toBeTruthy()
    expect(screen.getByRole('button')).toBeTruthy() // not applied: still there to retry
  })
})
