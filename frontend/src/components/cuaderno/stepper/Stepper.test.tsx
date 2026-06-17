import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import type { StepThroughResponse, Step, Var } from '../../../types/api'
import { Stepper } from './Stepper'

const v = (name: string, kind: Var['kind'], extra: Partial<Var> = {}): Var => ({ name, kind, ...extra })
const trace: Step[] = [
  { line: 255, event: 'call', changed: ['ref'], scope: [v('ref', 'large', { summary: 'FunctionRef', meta: '5 fields', children: [{ name: 'qualname', text: "'Foo.method'" }] })] },
  { line: 256, event: 'line', changed: ['qualname'], scope: [v('ref', 'large', { summary: 'FunctionRef', meta: '5 fields', children: [{ name: 'qualname', text: "'Foo.method'" }] }), v('qualname', 'scalar', { text: "'Foo.method'" })] },
  { line: 257, event: 'line', changed: [], scope: [v('qualname', 'scalar', { text: "'Foo.method'" })] },
  { line: 258, event: 'line', changed: ['parent'], scope: [v('parent', 'scalar', { text: 'None' })] },
]
const resp: StepThroughResponse = {
  kind: 'trace', trace,
  source_lines: [255, 256, 257, 258].map((num) => ({ num, text: `line ${num}` })),
  func_name: 'resolve_function_ref', file_line: 'intelligence/symbols.py:255', truncated: false,
}

describe('Stepper', () => {
  it('opens on step 1 of N and shows the counter', () => {
    render(<Stepper response={resp} onClose={() => {}} />)
    expect(screen.getByText('step 1 / 4')).toBeInTheDocument()
  })
  it('advances with the next button', async () => {
    render(<Stepper response={resp} onClose={() => {}} />)
    await userEvent.click(screen.getByRole('button', { name: '▶' }))
    expect(screen.getByText('step 2 / 4')).toBeInTheDocument()
  })
  it('clamps at the last step', async () => {
    render(<Stepper response={resp} onClose={() => {}} />)
    const next = screen.getByRole('button', { name: '▶' })
    for (let i = 0; i < 10; i++) await userEvent.click(next)
    expect(screen.getByText('step 4 / 4')).toBeInTheDocument()
  })
  it('jumps to the next change, skipping no-change steps', async () => {
    render(<Stepper response={resp} onClose={() => {}} />)
    // step 1 -> next change is step 2 (qualname). From 2, next change skips 3 (none) to 4 (parent).
    await userEvent.click(screen.getByRole('button', { name: /next change/ }))
    expect(screen.getByText('step 2 / 4')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /next change/ }))
    expect(screen.getByText('step 4 / 4')).toBeInTheDocument()
  })
  it('expands a large chip into its children', async () => {
    render(<Stepper response={resp} onClose={() => {}} />)
    expect(screen.queryByText("'Foo.method'")).not.toBeInTheDocument()
    await userEvent.click(screen.getByText('FunctionRef'))
    expect(screen.getByText("'Foo.method'")).toBeInTheDocument()
  })
  it('shows the truncated banner when truncated=true', () => {
    render(<Stepper response={{ ...resp, truncated: true }} onClose={() => {}} lang="en" />)
    expect(screen.getByText('Stopped at step 4 — trace truncated.')).toBeInTheDocument()
  })
  it('renders the raised card + banner on a raise terminal step', async () => {
    const raisedTrace: Step[] = [
      ...trace,
      { line: 263, event: 'raise', changed: [], scope: [v('qualname', 'scalar', { text: "'ghost'" })], raised: { type: 'KeyError', message: "'ghost'" } },
    ]
    render(<Stepper response={{ ...resp, trace: raisedTrace }} onClose={() => {}} lang="en" />)
    const next = screen.getByRole('button', { name: '▶' })
    for (let i = 0; i < 10; i++) await userEvent.click(next)
    expect(screen.getByText('Raised — this is the final step.')).toBeInTheDocument()
    expect(screen.getByText("KeyError: 'ghost'")).toBeInTheDocument()
  })
  it('suppresses the highlight slab on a stale anchor (line not in source_lines)', () => {
    // a trace whose first step line (999) is absent from source_lines → curIdx < 0
    const stale: StepThroughResponse = {
      ...resp,
      trace: [{ line: 999, event: 'call', changed: ['x'], scope: [v('x', 'scalar', { text: '1' })] }],
    }
    const { container } = render(<Stepper response={stale} onClose={() => {}} />)
    // the slab carries the accent left border; on a stale anchor it must not render
    const slab = container.querySelector('[data-testid="hl-slab"]')
    expect(slab).toBeNull()
  })
  it('fires onClose from the × button', async () => {
    const onClose = vi.fn()
    render(<Stepper response={resp} onClose={onClose} />)
    await userEvent.click(screen.getByRole('button', { name: '×' }))
    expect(onClose).toHaveBeenCalled()
  })

  // Issue 2: banner must only say "final step" when it IS the final step
  it('does NOT show raised-final banner on a mid-trace raise step', async () => {
    // Trace: raise at step 1 of 3, two more steps follow → not the final step
    const midRaiseTrace: Step[] = [
      { line: 10, event: 'raise', changed: [], scope: [], raised: { type: 'ValueError', message: 'mid' } },
      { line: 11, event: 'line', changed: ['x'], scope: [v('x', 'scalar', { text: '1' })] },
      { line: 12, event: 'return', changed: [], scope: [] },
    ]
    render(<Stepper response={{ ...resp, trace: midRaiseTrace }} onClose={() => {}} lang="en" />)
    // On step 1 (a raise event but NOT the last step), the final-step banner must NOT appear
    expect(screen.queryByText('Raised — this is the final step.')).not.toBeInTheDocument()
  })

  // Issue 2: banner DOES appear when the raise IS on the last step
  it('shows raised-final banner only when raise step is also the last step', async () => {
    const terminalRaiseTrace: Step[] = [
      { line: 10, event: 'line', changed: [], scope: [] },
      { line: 11, event: 'raise', changed: [], scope: [], raised: { type: 'ValueError', message: 'end' } },
    ]
    render(<Stepper response={{ ...resp, trace: terminalRaiseTrace }} onClose={() => {}} lang="en" />)
    const next = screen.getByRole('button', { name: '▶' })
    await userEvent.click(next)
    expect(screen.getByText('Raised — this is the final step.')).toBeInTheDocument()
  })

  // Issue 3: step and expanded reset when response prop changes — synchronously, no flash
  it('resets step and expansion synchronously when response identity changes (no stale-expansion flash)', async () => {
    // Build a trace where the large var's child text is unique (not repeated in scope)
    const deepTrace: Step[] = [
      { line: 255, event: 'call', changed: ['box'], scope: [v('box', 'large', { summary: 'Wrapper', meta: '1 field', children: [{ name: 'inner', text: '__UNIQUE_CHILD__' }] })] },
      { line: 256, event: 'line', changed: ['x'], scope: [v('x', 'scalar', { text: '99' })] },
      { line: 257, event: 'line', changed: [], scope: [v('x', 'scalar', { text: '99' })] },
    ]
    const deepResp: StepThroughResponse = { ...resp, trace: deepTrace }
    const { rerender } = render(<Stepper response={deepResp} onClose={() => {}} />)
    // Advance to step 2
    const next = screen.getByRole('button', { name: '▶' })
    await userEvent.click(next)
    expect(screen.getByText('step 2 / 3')).toBeInTheDocument()
    // Expand 'box' chip while still on step 1 (go back first so box is in scope)
    await userEvent.click(screen.getByRole('button', { name: '◀' }))
    expect(screen.getByText('step 1 / 3')).toBeInTheDocument()
    await userEvent.click(screen.getByText('Wrapper'))
    // After expansion, the unique child text appears
    expect(screen.getByText('__UNIQUE_CHILD__')).toBeInTheDocument()
    // Advance to step 2 again so step counter is not 1
    await userEvent.click(next)
    expect(screen.getByText('step 2 / 3')).toBeInTheDocument()
    // Now swap to a different response identity.
    // The reset must happen synchronously during the render, not in a post-render
    // effect (useEffect would cause a 1-frame flash where stale expanded children
    // are still visible).  We do NOT wrap in act() so that the assertion checks
    // the DOM as committed by the rerender itself, before any effects could flush.
    const resp2: StepThroughResponse = { ...deepResp, func_name: 'other_func' }
    rerender(<Stepper response={resp2} onClose={() => {}} />)
    // Step must be back to 1 immediately — no effect flush needed
    expect(screen.getByText('step 1 / 3')).toBeInTheDocument()
    // Expansion must already be cleared — unique child must not appear even
    // before any effect has run.  This would FAIL with a useEffect-based reset
    // because the effect fires after paint (stale expanded map still active).
    expect(screen.queryByText('__UNIQUE_CHILD__')).not.toBeInTheDocument()
  })

  // Issue 4: slabBg/slabBorder must be neutral (accent) when truncated=true, even if raised flag is set
  it('uses accent slab colours (not red) on the current step when truncated=true, even when the step is a raise', () => {
    // Use line 255 which IS in resp.source_lines so the slab renders (curIdx >= 0)
    const raisedTruncTrace: Step[] = [
      { line: 255, event: 'raise', changed: [], scope: [], raised: { type: 'RuntimeError', message: 'cut' } },
    ]
    const { container } = render(
      <Stepper response={{ ...resp, trace: raisedTruncTrace, truncated: true }} onClose={() => {}} lang="en" />
    )
    const slab = container.querySelector<HTMLElement>('[data-testid="hl-slab"]')
    expect(slab).not.toBeNull()
    // slabBg must NOT be the negative (red) token when truncated=true
    const bg = slab!.style.background
    expect(bg).not.toBe('var(--neg)')
    // slabBorder must also not be red
    expect(slab!.style.borderLeftColor).not.toBe('var(--neg-ink)')
  })
})
