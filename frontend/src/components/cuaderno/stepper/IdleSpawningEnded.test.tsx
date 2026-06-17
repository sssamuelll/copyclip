/**
 * Behavior tests for IdleInvitation, Spawning, and EndedCards.
 *
 * Each component had zero test coverage. This file verifies:
 * - IdleInvitation: renders the anchored-function metadata, fires onStepThrough
 *   from the action button, and fires onClose from the × button.
 * - Spawning: renders the callText + progress bar animation classes + the
 *   preparing/capturing copy.
 * - EndedCards: 3-way reason dispatch (closed/exited → runtime-closed,
 *   evicted → evicted, error → spawn-error) with correct tokens, titles,
 *   body copy, button labels, and callbacks.
 *
 * All assertions are written against real DOM output so that breaking the
 * impl causes the tests to fail (no hollow snapshot checks).
 */
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { IdleInvitation } from './IdleInvitation'
import { Spawning } from './Spawning'
import { EndedCards } from './EndedCards'

// ---------------------------------------------------------------------------
// IdleInvitation
// ---------------------------------------------------------------------------

describe('IdleInvitation', () => {
  const defaults = {
    funcName: 'compute_risk',
    fileLine: 'risk/engine.py:42',
    onStepThrough: vi.fn(),
    onClose: vi.fn(),
  }

  it('renders the funcName in the header and in the center body', () => {
    render(<IdleInvitation {...defaults} />)
    // Should appear at least twice: header monospace span + center body
    const els = screen.getAllByText('compute_risk')
    expect(els.length).toBeGreaterThanOrEqual(2)
  })

  it('renders the fileLine under the funcName in the center body', () => {
    render(<IdleInvitation {...defaults} />)
    expect(screen.getByText('risk/engine.py:42')).toBeInTheDocument()
  })

  it('fires onStepThrough when the action button is clicked', () => {
    const onStepThrough = vi.fn()
    render(<IdleInvitation {...defaults} onStepThrough={onStepThrough} />)
    // Button text comes from t('playground_step_through') = "Step through"
    const btn = screen.getByRole('button', { name: /step through/i })
    fireEvent.click(btn)
    expect(onStepThrough).toHaveBeenCalledTimes(1)
  })

  it('does NOT fire onStepThrough when the × button is clicked', () => {
    const onStepThrough = vi.fn()
    const onClose = vi.fn()
    render(<IdleInvitation {...defaults} onStepThrough={onStepThrough} onClose={onClose} />)
    const closeBtn = screen.getByRole('button', { name: '×' })
    fireEvent.click(closeBtn)
    expect(onClose).toHaveBeenCalledTimes(1)
    expect(onStepThrough).not.toHaveBeenCalled()
  })

  it('fires onClose from the × button', () => {
    const onClose = vi.fn()
    render(<IdleInvitation {...defaults} onClose={onClose} />)
    fireEvent.click(screen.getByRole('button', { name: '×' }))
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('renders inside a .stepper-widget container (same chrome as Stepper)', () => {
    const { container } = render(<IdleInvitation {...defaults} />)
    expect(container.querySelector('.stepper-widget')).not.toBeNull()
  })

  it('shows the playground_anchored label (en: "Anchored function")', () => {
    render(<IdleInvitation {...defaults} lang="en" />)
    expect(screen.getByText('Anchored function')).toBeInTheDocument()
  })

  it('shows the anchored label in Spanish when lang="es"', () => {
    render(<IdleInvitation {...defaults} lang="es" />)
    expect(screen.getByText('Función anclada')).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Spawning
// ---------------------------------------------------------------------------

describe('Spawning', () => {
  const defaults = {
    funcName: 'fit_model',
    callText: 'fit_model(X_train, y_train)',
  }

  it('renders the funcName in the header', () => {
    render(<Spawning {...defaults} />)
    expect(screen.getByText('fit_model')).toBeInTheDocument()
  })

  it('renders the callText in the body', () => {
    render(<Spawning {...defaults} />)
    expect(screen.getByText('fit_model(X_train, y_train)')).toBeInTheDocument()
  })

  it('renders the stepper-sweep animation class for the progress bar', () => {
    const { container } = render(<Spawning {...defaults} />)
    expect(container.querySelector('.stepper-sweep')).not.toBeNull()
  })

  it('renders the stepper-pulse animation class for the pulse dot', () => {
    const { container } = render(<Spawning {...defaults} />)
    expect(container.querySelector('.stepper-pulse')).not.toBeNull()
  })

  it('shows the playground_preparing_capturing copy (en)', () => {
    render(<Spawning {...defaults} lang="en" />)
    expect(screen.getByText('running once · capturing trace')).toBeInTheDocument()
  })

  it('shows the preparing copy in Spanish when lang="es"', () => {
    render(<Spawning {...defaults} lang="es" />)
    expect(screen.getByText('corriendo una vez · capturando la traza')).toBeInTheDocument()
  })

  it('renders inside a .stepper-widget container', () => {
    const { container } = render(<Spawning {...defaults} />)
    expect(container.querySelector('.stepper-widget')).not.toBeNull()
  })
})

// ---------------------------------------------------------------------------
// EndedCards — 3-way reason dispatch
// ---------------------------------------------------------------------------

describe('EndedCards', () => {
  const defaults = {
    funcName: 'emit_event',
    reason: 'closed' as const,
    onRetry: vi.fn(),
    onClose: vi.fn(),
  }

  it('renders inside a .stepper-widget container', () => {
    const { container } = render(<EndedCards {...defaults} />)
    expect(container.querySelector('.stepper-widget')).not.toBeNull()
  })

  it('shows the funcName in the header', () => {
    render(<EndedCards {...defaults} />)
    expect(screen.getByText('emit_event')).toBeInTheDocument()
  })

  // --- reason: 'closed' (falls through to runtime-closed bucket) ---

  it('reason=closed: shows playground_runtime_closed title', () => {
    render(<EndedCards {...defaults} reason="closed" lang="en" />)
    expect(screen.getByText('Runtime closed')).toBeInTheDocument()
  })

  it('reason=closed: shows runtime_closed_body copy', () => {
    render(<EndedCards {...defaults} reason="closed" lang="en" />)
    expect(screen.getByText(/sandbox shut down after idle/i)).toBeInTheDocument()
  })

  it('reason=closed: retry button says "Reopen"', () => {
    render(<EndedCards {...defaults} reason="closed" lang="en" />)
    expect(screen.getByRole('button', { name: /reopen/i })).toBeInTheDocument()
  })

  // --- reason: 'exited' (same bucket as closed) ---

  it('reason=exited: shows playground_runtime_closed title', () => {
    render(<EndedCards {...defaults} reason="exited" lang="en" />)
    expect(screen.getByText('Runtime closed')).toBeInTheDocument()
  })

  it('reason=exited: retry button says "Reopen"', () => {
    render(<EndedCards {...defaults} reason="exited" lang="en" />)
    expect(screen.getByRole('button', { name: /reopen/i })).toBeInTheDocument()
  })

  // --- reason: 'evicted' ---

  it('reason=evicted: shows playground_evicted_title', () => {
    render(<EndedCards {...defaults} reason="evicted" lang="en" />)
    expect(screen.getByText('Evicted')).toBeInTheDocument()
  })

  it('reason=evicted: shows evicted_body copy', () => {
    render(<EndedCards {...defaults} reason="evicted" lang="en" />)
    expect(screen.getByText(/another example took this slot/i)).toBeInTheDocument()
  })

  it('reason=evicted: retry button says "Bring it back"', () => {
    render(<EndedCards {...defaults} reason="evicted" lang="en" />)
    expect(screen.getByRole('button', { name: /bring it back/i })).toBeInTheDocument()
  })

  // --- reason: 'error' ---

  it('reason=error: shows playground_spawn_error title', () => {
    render(<EndedCards {...defaults} reason="error" lang="en" />)
    expect(screen.getByText('Spawn error')).toBeInTheDocument()
  })

  it('reason=error: shows spawn_error_body copy when no message prop', () => {
    render(<EndedCards {...defaults} reason="error" lang="en" />)
    expect(screen.getByText(/playground didn't start/i)).toBeInTheDocument()
  })

  it('reason=error: shows custom message when message prop is provided', () => {
    render(<EndedCards {...defaults} reason="error" message="connection refused" lang="en" />)
    expect(screen.getByText('connection refused')).toBeInTheDocument()
  })

  it('reason=error: retry button says "Try again"', () => {
    render(<EndedCards {...defaults} reason="error" lang="en" />)
    expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument()
  })

  // --- callback wiring ---

  it('fires onRetry when the retry button is clicked', () => {
    const onRetry = vi.fn()
    render(<EndedCards {...defaults} onRetry={onRetry} />)
    const btns = screen.getAllByRole('button')
    // The retry button is NOT the × button; find it by excluding ×
    const retryBtn = btns.find((b) => b.getAttribute('aria-label') !== '×')
    expect(retryBtn).toBeDefined()
    fireEvent.click(retryBtn!)
    expect(onRetry).toHaveBeenCalledTimes(1)
  })

  it('fires onClose when the × button is clicked', () => {
    const onClose = vi.fn()
    render(<EndedCards {...defaults} onClose={onClose} />)
    fireEvent.click(screen.getByRole('button', { name: '×' }))
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('does NOT fire onRetry when the × button is clicked', () => {
    const onRetry = vi.fn()
    render(<EndedCards {...defaults} onRetry={onRetry} />)
    fireEvent.click(screen.getByRole('button', { name: '×' }))
    expect(onRetry).not.toHaveBeenCalled()
  })

  // --- Spanish locale ---

  it('shows Spanish labels when lang="es"', () => {
    render(<EndedCards {...defaults} reason="evicted" lang="es" />)
    expect(screen.getByText('Desalojado')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /traerlo de vuelta/i })).toBeInTheDocument()
  })
})
