/**
 * Behavioral contract tests for the --neg token usage in Stepper.
 *
 * These replace the former PlaygroundWidget.css.test.ts which asserted CSS
 * selector presence in cuaderno.css.  That test was orphaned: the
 * .playground-trace-* classes it listed were in deleted flat-trace JSX and no
 * longer appear in the live rendered markup (Stepper uses inline styles).
 * The --neg guarantee for the raised exception card had moved to Stepper.tsx
 * inline styles and was completely unguarded.
 *
 * These tests verify the actual rendered DOM: the Stepper emits var(--neg) on
 * the raised exception card and on the highlight slab, and does NOT emit it
 * when the trace is truncated.
 */
import { render } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import type { StepThroughResponse, Step, Var } from '../../../types/api'
import { Stepper } from '../stepper/Stepper'

const v = (name: string, kind: Var['kind'], extra: Partial<Var> = {}): Var => ({
  name,
  kind,
  ...extra,
})

const baseSourceLines = [{ num: 10, text: 'return x' }]

const baseResp: StepThroughResponse = {
  kind: 'trace',
  trace: [],
  source_lines: baseSourceLines,
  func_name: 'fn',
  file_line: 'a.py:10',
  truncated: false,
}

/** Build a terminal raise trace (single raise step so cur === total). */
function raisedResp(extra: Partial<StepThroughResponse> = {}): StepThroughResponse {
  const raiseStep: Step = {
    line: 10,
    event: 'raise',
    changed: [],
    scope: [v('x', 'scalar', { text: '1' })],
    raised: { type: 'KeyError', message: "'ghost'" },
  }
  return { ...baseResp, trace: [raiseStep], ...extra }
}

describe('Stepper — --neg token contract (raised exception card)', () => {
  it('raised exception card uses background:var(--neg) and border var(--neg-line) on a terminal raise step, and renders exception text', () => {
    const { container, getByText } = render(
      <Stepper response={raisedResp()} onClose={() => {}} />,
    )
    // The Stepper renders the card with `border:1px solid var(--neg-line)` (shorthand).
    // JSDOM stores the shorthand on el.style.border, NOT on el.style.borderColor.
    // Checking el.style.border.includes('var(--neg-line)') is the reliable way.
    const raisedCard = Array.from(container.querySelectorAll<HTMLElement>('div')).find(
      (el) =>
        el.style.background === 'var(--neg)' &&
        el.style.border.includes('var(--neg-line)'),
    )
    expect(raisedCard, 'raised exception card must exist with background:var(--neg) and border containing var(--neg-line)').not.toBeUndefined()
    // The card must also render the exception type and message
    expect(getByText("KeyError: 'ghost'"), 'exception type:message must render inside the card').toBeInTheDocument()
  })

  it('raised exception card is absent when there is no raised field', () => {
    const noRaise: Step = {
      line: 10,
      event: 'line',
      changed: [],
      scope: [v('x', 'scalar', { text: '1' })],
    }
    const { container, queryByText } = render(
      <Stepper response={{ ...baseResp, trace: [noRaise] }} onClose={() => {}} />,
    )
    // The card must not exist: no element should have both --neg background and --neg-line border
    const raisedCard = Array.from(container.querySelectorAll<HTMLElement>('div')).find(
      (el) =>
        el.style.background === 'var(--neg)' &&
        el.style.border.includes('var(--neg-line)'),
    )
    expect(raisedCard, 'no raised card when step has no raised field').toBeUndefined()
    // Additionally: the exception text must not appear at all
    expect(queryByText(/KeyError/), 'exception text must not render when no raised field').toBeNull()
  })
})

describe('Stepper — --neg token contract (highlight slab)', () => {
  it('slab uses background:var(--neg) when raise is terminal and not truncated', () => {
    const { container } = render(
      <Stepper response={raisedResp({ truncated: false })} onClose={() => {}} />,
    )
    const slab = container.querySelector<HTMLElement>('[data-testid="hl-slab"]')
    expect(slab, 'slab must render when line is in source_lines').not.toBeNull()
    expect(slab!.style.background).toBe('var(--neg)')
  })

  it('slab uses --neg background when raise is terminal even when truncated=true (raised wins over truncated)', () => {
    const { container } = render(
      <Stepper response={raisedResp({ truncated: true })} onClose={() => {}} />,
    )
    const slab = container.querySelector<HTMLElement>('[data-testid="hl-slab"]')
    expect(slab, 'slab must render when line is in source_lines').not.toBeNull()
    // After the fix: raised wins over truncated — slab IS red
    expect(slab!.style.background).toBe('var(--neg)')
  })

  it('slab uses accent background on a normal line step', () => {
    const lineStep: Step = {
      line: 10,
      event: 'line',
      changed: [],
      scope: [v('x', 'scalar', { text: '1' })],
    }
    const { container } = render(
      <Stepper response={{ ...baseResp, trace: [lineStep] }} onClose={() => {}} />,
    )
    const slab = container.querySelector<HTMLElement>('[data-testid="hl-slab"]')
    expect(slab, 'slab must render on a normal line step').not.toBeNull()
    expect(slab!.style.background).toBe('var(--accent-soft)')
  })
})
