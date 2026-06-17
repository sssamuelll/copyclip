/**
 * PlaygroundWidget — trace branch must delegate to <Stepper>, not render a
 * flat <ol>/<li> trace itself.
 */
import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import type { StepThroughResponse, PlaygroundWidgetData, Citation } from '../../../types/api'

// Mock the slot store so we can inject a trace state without running the full API
vi.mock('../playgroundSlot', () => ({
  subscribe: vi.fn(() => () => {}),
  getState: vi.fn(),
  launch: vi.fn(),
  close: vi.fn(),
}))

import { getState } from '../playgroundSlot'
import { PlaygroundWidget } from './PlaygroundWidget'

const TRACE_RESP: StepThroughResponse = {
  kind: 'trace',
  trace: [{ line: 255, event: 'call', changed: ['x'], scope: [{ name: 'x', kind: 'scalar', text: '42' }] }],
  source_lines: [{ num: 255, text: 'def f(x): return x' }],
  func_name: 'my_func',
  file_line: 'demo.py:255',
  truncated: false,
}

const WIDGET: PlaygroundWidgetData = {
  kind: 'playground',
  function_ref: { file: 'demo.py', name: 'my_func' },
  breadcrumb: 'Step through my_func',
}

const MY_KEY = 'demo.py:my_func:'
const noop = () => {}
const noopCitation = (_: Citation) => {}

beforeEach(() => {
  vi.mocked(getState).mockReturnValue({
    kind: 'trace',
    widgetKey: MY_KEY,
    response: TRACE_RESP,
    token: 1,
  })
})

describe('PlaygroundWidget — trace branch', () => {
  it('renders the Stepper widget (stepper-widget class), not a flat ol/li trace', () => {
    const { container } = render(
      <PlaygroundWidget widget={WIDGET} onOpenCitation={noopCitation} lang="en" />
    )
    // Stepper renders a .stepper-widget div
    expect(container.querySelector('.stepper-widget')).not.toBeNull()
    // The old flat trace must NOT be present
    expect(container.querySelector('.playground-trace')).toBeNull()
    expect(container.querySelector('.playground-trace-steps')).toBeNull()
  })

  it('shows the step counter from Stepper (step N / M)', () => {
    render(<PlaygroundWidget widget={WIDGET} onOpenCitation={noopCitation} lang="en" />)
    expect(screen.getByText('step 1 / 1')).toBeInTheDocument()
  })

  it('shows the func_name from the trace response in the Stepper header', () => {
    render(<PlaygroundWidget widget={WIDGET} onOpenCitation={noopCitation} lang="en" />)
    // Stepper header shows func_name in mono span
    expect(screen.getAllByText('my_func').length).toBeGreaterThan(0)
  })
})
