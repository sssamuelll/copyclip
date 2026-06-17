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
    // The retry button is the one that is not ×
    const btns = screen.getAllByRole('button')
    const retryBtn = btns.find((b) => b.getAttribute('aria-label') !== '×')
    expect(retryBtn).toBeDefined()
    fireEvent.click(retryBtn!)
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
