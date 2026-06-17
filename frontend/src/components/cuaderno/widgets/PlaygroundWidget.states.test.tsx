/**
 * PlaygroundWidget — wiring tests for idle, spawning, and ended states.
 *
 * These tests verify that PlaygroundWidget delegates to the dedicated
 * IdleInvitation, Spawning, and EndedCards sub-components instead of
 * using inline text-based rendering.  Before the fix these three
 * components were dead code — imported nowhere, rendered by no one.
 *
 * Each test is written so that a broken implementation (e.g. using inline
 * text instead of the component) causes a failure:
 *  - We assert the animated CSS class / stepper-ghost class that only the
 *    real component emits.
 *  - We assert that inline fallback markup is absent.
 *  - For idle we assert that the IdleInvitation action button is present.
 *  - For ended we assert the EndedCards × close button (aria-label="×").
 */
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import type { PlaygroundWidgetData, Citation } from '../../../types/api'

vi.mock('../playgroundSlot', () => ({
  subscribe: vi.fn(() => () => {}),
  getState: vi.fn(),
  launch: vi.fn(),
  close: vi.fn(),
}))

import { getState, launch, close } from '../playgroundSlot'
import { PlaygroundWidget } from './PlaygroundWidget'

const WIDGET: PlaygroundWidgetData = {
  kind: 'playground',
  function_ref: { file: 'demo.py', name: 'my_func' },
  breadcrumb: 'Step through my_func',
}
const MY_KEY = 'demo.py:my_func:'
const noopCitation = (_: Citation) => {}

// ---------------------------------------------------------------------------
// idle state — slot.kind === 'empty'
// renders IdleInvitation, NOT a plain run-button widget
// ---------------------------------------------------------------------------

describe('PlaygroundWidget — idle state delegates to IdleInvitation', () => {
  beforeEach(() => {
    vi.mocked(getState).mockReturnValue({ kind: 'empty' })
  })

  it('renders the .stepper-widget container (from IdleInvitation)', () => {
    const { container } = render(
      <PlaygroundWidget widget={WIDGET} onOpenCitation={noopCitation} lang="en" />
    )
    expect(container.querySelector('.stepper-widget')).not.toBeNull()
  })

  it('shows the "Step through" action button from IdleInvitation', () => {
    render(<PlaygroundWidget widget={WIDGET} onOpenCitation={noopCitation} lang="en" />)
    expect(screen.getByRole('button', { name: /step through/i })).toBeInTheDocument()
  })

  it('shows "Anchored function" label from IdleInvitation', () => {
    render(<PlaygroundWidget widget={WIDGET} onOpenCitation={noopCitation} lang="en" />)
    expect(screen.getByText('Anchored function')).toBeInTheDocument()
  })

  it('calls launch() when the Step through button is clicked', () => {
    vi.mocked(launch).mockResolvedValue(undefined)
    render(<PlaygroundWidget widget={WIDGET} onOpenCitation={noopCitation} lang="en" />)
    fireEvent.click(screen.getByRole('button', { name: /step through/i }))
    expect(launch).toHaveBeenCalledWith(MY_KEY, expect.objectContaining({ source: 'cuaderno' }))
  })

  it('does NOT show the old plain-text run-button widget (no .widget-body)', () => {
    const { container } = render(
      <PlaygroundWidget widget={WIDGET} onOpenCitation={noopCitation} lang="en" />
    )
    // The old inline widget had a .widget-body div; IdleInvitation does not.
    expect(container.querySelector('.widget-body')).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// spawning state — slot.kind === 'spawning'
// renders Spawning, NOT inline playground-preparing div
// ---------------------------------------------------------------------------

describe('PlaygroundWidget — spawning state delegates to Spawning', () => {
  beforeEach(() => {
    vi.mocked(getState).mockReturnValue({
      kind: 'spawning',
      widgetKey: MY_KEY,
      token: 1,
    })
  })

  it('renders the .stepper-widget container (from Spawning)', () => {
    const { container } = render(
      <PlaygroundWidget widget={WIDGET} onOpenCitation={noopCitation} lang="en" />
    )
    expect(container.querySelector('.stepper-widget')).not.toBeNull()
  })

  it('renders the .stepper-sweep progress bar animation class (from Spawning)', () => {
    const { container } = render(
      <PlaygroundWidget widget={WIDGET} onOpenCitation={noopCitation} lang="en" />
    )
    expect(container.querySelector('.stepper-sweep')).not.toBeNull()
  })

  it('renders the .stepper-pulse animation class (from Spawning)', () => {
    const { container } = render(
      <PlaygroundWidget widget={WIDGET} onOpenCitation={noopCitation} lang="en" />
    )
    expect(container.querySelector('.stepper-pulse')).not.toBeNull()
  })

  it('does NOT use the old inline .playground-preparing div', () => {
    const { container } = render(
      <PlaygroundWidget widget={WIDGET} onOpenCitation={noopCitation} lang="en" />
    )
    expect(container.querySelector('.playground-preparing')).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// ended state — slot.kind === 'ended', reason variations
// renders EndedCards, NOT inline playground-status-note div
// ---------------------------------------------------------------------------

describe('PlaygroundWidget — ended state delegates to EndedCards', () => {
  it('renders .stepper-widget container for reason=closed', () => {
    vi.mocked(getState).mockReturnValue({ kind: 'ended', widgetKey: MY_KEY, reason: 'closed' })
    const { container } = render(
      <PlaygroundWidget widget={WIDGET} onOpenCitation={noopCitation} lang="en" />
    )
    expect(container.querySelector('.stepper-widget')).not.toBeNull()
  })

  it('shows "Runtime closed" title for reason=closed', () => {
    vi.mocked(getState).mockReturnValue({ kind: 'ended', widgetKey: MY_KEY, reason: 'closed' })
    render(<PlaygroundWidget widget={WIDGET} onOpenCitation={noopCitation} lang="en" />)
    expect(screen.getByText('Runtime closed')).toBeInTheDocument()
  })

  it('shows "Evicted" title for reason=evicted', () => {
    vi.mocked(getState).mockReturnValue({ kind: 'ended', widgetKey: MY_KEY, reason: 'evicted' })
    render(<PlaygroundWidget widget={WIDGET} onOpenCitation={noopCitation} lang="en" />)
    expect(screen.getByText('Evicted')).toBeInTheDocument()
  })

  it('shows "Spawn error" title for reason=error', () => {
    vi.mocked(getState).mockReturnValue({ kind: 'ended', widgetKey: MY_KEY, reason: 'error' })
    render(<PlaygroundWidget widget={WIDGET} onOpenCitation={noopCitation} lang="en" />)
    expect(screen.getByText('Spawn error')).toBeInTheDocument()
  })

  it('shows custom error message from slot.message for reason=error', () => {
    vi.mocked(getState).mockReturnValue({
      kind: 'ended',
      widgetKey: MY_KEY,
      reason: 'error',
      message: 'port 5000 already in use',
    })
    render(<PlaygroundWidget widget={WIDGET} onOpenCitation={noopCitation} lang="en" />)
    expect(screen.getByText('port 5000 already in use')).toBeInTheDocument()
  })

  it('has a × close button from EndedCards', () => {
    vi.mocked(getState).mockReturnValue({ kind: 'ended', widgetKey: MY_KEY, reason: 'closed' })
    render(<PlaygroundWidget widget={WIDGET} onOpenCitation={noopCitation} lang="en" />)
    expect(screen.getByRole('button', { name: '×' })).toBeInTheDocument()
  })

  it('calls close() from the × button on EndedCards', () => {
    vi.mocked(getState).mockReturnValue({ kind: 'ended', widgetKey: MY_KEY, reason: 'closed' })
    render(<PlaygroundWidget widget={WIDGET} onOpenCitation={noopCitation} lang="en" />)
    fireEvent.click(screen.getByRole('button', { name: '×' }))
    expect(close).toHaveBeenCalled()
  })

  it('calls launch() (retry) from the retry button on EndedCards', () => {
    vi.mocked(launch).mockResolvedValue(undefined)
    vi.mocked(getState).mockReturnValue({ kind: 'ended', widgetKey: MY_KEY, reason: 'closed' })
    render(<PlaygroundWidget widget={WIDGET} onOpenCitation={noopCitation} lang="en" />)
    // Find retry button by its accessible name, not by excluding ×
    const retryBtn = screen.getByRole('button', { name: /reopen/i })
    fireEvent.click(retryBtn)
    expect(launch).toHaveBeenCalledWith(MY_KEY, expect.objectContaining({ source: 'cuaderno' }))
  })

  it('does NOT use the old inline .playground-status-note div', () => {
    vi.mocked(getState).mockReturnValue({ kind: 'ended', widgetKey: MY_KEY, reason: 'evicted' })
    const { container } = render(
      <PlaygroundWidget widget={WIDGET} onOpenCitation={noopCitation} lang="en" />
    )
    expect(container.querySelector('.playground-status-note')).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// Issue 1: idle widget when slot is owned by a DIFFERENT widget
// The × must NOT be present — pressing it would call close() and kill an
// active playground that belongs to a completely different function.
// ---------------------------------------------------------------------------

describe('PlaygroundWidget — idle when slot owned by another widget has no × button', () => {
  const OTHER_KEY = 'other.py:other_func:'

  it('slot kind=spawning owned by other: idle widget shows NO × button', () => {
    vi.mocked(getState).mockReturnValue({ kind: 'spawning', widgetKey: OTHER_KEY, token: 1 })
    render(<PlaygroundWidget widget={WIDGET} onOpenCitation={noopCitation} lang="en" />)
    expect(screen.queryByRole('button', { name: '×' })).toBeNull()
  })

  it('slot kind=live owned by other: idle widget shows NO × button', () => {
    vi.mocked(getState).mockReturnValue({
      kind: 'live',
      widgetKey: OTHER_KEY,
      playgroundId: 'pg-99',
      iframeUrl: '/playground/pg-99',
      token: 1,
    })
    render(<PlaygroundWidget widget={WIDGET} onOpenCitation={noopCitation} lang="en" />)
    expect(screen.queryByRole('button', { name: '×' })).toBeNull()
  })

  it('slot kind=trace owned by other: idle widget shows NO × button', () => {
    vi.mocked(getState).mockReturnValue({
      kind: 'trace',
      widgetKey: OTHER_KEY,
      token: 1,
      response: { kind: 'trace', trace: [], source_lines: [], func_name: 'f', file_line: 'a.py:1', truncated: false },
    })
    render(<PlaygroundWidget widget={WIDGET} onOpenCitation={noopCitation} lang="en" />)
    expect(screen.queryByRole('button', { name: '×' })).toBeNull()
  })

  it('slot kind=empty: idle widget DOES show a × button', () => {
    vi.mocked(getState).mockReturnValue({ kind: 'empty' })
    render(<PlaygroundWidget widget={WIDGET} onOpenCitation={noopCitation} lang="en" />)
    expect(screen.getByRole('button', { name: '×' })).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Issue 2: citation and breadcrumb must render in idle, spawning, ended states
// ---------------------------------------------------------------------------

const CITATION_WIDGET: PlaygroundWidgetData = {
  kind: 'playground',
  function_ref: { file: 'demo.py', name: 'my_func' },
  breadcrumb: 'Step through my_func',
  citation: { kind: 'path', path: 'demo.py', line_start: 10, line_end: 20 },
}

describe('PlaygroundWidget — citation and breadcrumb in non-live states', () => {
  it('idle state: renders the breadcrumb text', () => {
    vi.mocked(getState).mockReturnValue({ kind: 'empty' })
    render(<PlaygroundWidget widget={CITATION_WIDGET} onOpenCitation={noopCitation} lang="en" />)
    expect(screen.getByText('Step through my_func')).toBeInTheDocument()
  })

  it('idle state: renders the citation chip', () => {
    vi.mocked(getState).mockReturnValue({ kind: 'empty' })
    const { container } = render(
      <PlaygroundWidget widget={CITATION_WIDGET} onOpenCitation={noopCitation} lang="en" />
    )
    expect(container.querySelector('.cite')).not.toBeNull()
  })

  it('spawning state: renders the breadcrumb text in the .playground-breadcrumb span', () => {
    vi.mocked(getState).mockReturnValue({ kind: 'spawning', widgetKey: MY_KEY, token: 1 })
    const { container } = render(
      <PlaygroundWidget widget={CITATION_WIDGET} onOpenCitation={noopCitation} lang="en" />
    )
    // The breadcrumb may also be the callText, so we check via the CSS class
    // rather than getByText to avoid ambiguity.
    expect(container.querySelector('.playground-breadcrumb')).not.toBeNull()
    expect(container.querySelector('.playground-breadcrumb')?.textContent).toBe('Step through my_func')
  })

  it('spawning state: renders the citation chip', () => {
    vi.mocked(getState).mockReturnValue({ kind: 'spawning', widgetKey: MY_KEY, token: 1 })
    const { container } = render(
      <PlaygroundWidget widget={CITATION_WIDGET} onOpenCitation={noopCitation} lang="en" />
    )
    expect(container.querySelector('.cite')).not.toBeNull()
  })

  it('ended state: renders the breadcrumb text', () => {
    vi.mocked(getState).mockReturnValue({ kind: 'ended', widgetKey: MY_KEY, reason: 'closed' })
    render(<PlaygroundWidget widget={CITATION_WIDGET} onOpenCitation={noopCitation} lang="en" />)
    expect(screen.getByText('Step through my_func')).toBeInTheDocument()
  })

  it('ended state: renders the citation chip', () => {
    vi.mocked(getState).mockReturnValue({ kind: 'ended', widgetKey: MY_KEY, reason: 'closed' })
    const { container } = render(
      <PlaygroundWidget widget={CITATION_WIDGET} onOpenCitation={noopCitation} lang="en" />
    )
    expect(container.querySelector('.cite')).not.toBeNull()
  })
})
