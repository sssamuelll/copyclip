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
})
