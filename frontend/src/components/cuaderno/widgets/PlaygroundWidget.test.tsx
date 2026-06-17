/**
 * PlaygroundWidget — full integration tests (Task 10, two deferred concerns).
 *
 * Deferred concern 1 (Task 4): RENDER TEST — trace branch renders func_name,
 * file_line, step rows, close button, and truncated badge; fallback branch mounts
 * the iframe box; free-text preview/edit re-capture flow reaches launch.
 *
 * Deferred concern 2 (Task 6): LOCALIZED TRUNCATED BADGE — the badge is driven
 * by the playground_truncated i18n key with the {n} step-count param, not
 * hardcoded English. Asserted below with both en and es locales.
 *
 * Unlike the PlaygroundWidget.states.test.tsx (slot-mocked, unit-level),
 * these tests run against the REAL slot store and mock only the api client,
 * so they exercise the full idle → preview → spawning → stepper/iframe path.
 */
import { render, screen, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, beforeEach, vi } from 'vitest'
import type { StepThroughResponse, FallbackResponse, PlaygroundWidgetData } from '../../../types/api'

// vi.mock is hoisted — inline fns in the factory; grab via vi.mocked() after import
vi.mock('../../../api/client', () => ({
  api: {
    launchPlayground: vi.fn(),
    closePlayground: vi.fn(() => Promise.resolve({ ok: true })),
    playgroundStatus: vi.fn(() => Promise.resolve({ status: 'running', id: '1' })),
    playgroundList: vi.fn(() => Promise.resolve({ items: [] })),
  },
}))

import { api } from '../../../api/client'
import { PlaygroundWidget } from './PlaygroundWidget'
import { _resetForTests } from '../playgroundSlot'

const launchPlayground = vi.mocked(api.launchPlayground)
const closePlayground = vi.mocked(api.closePlayground)

const fn = { file: 'intelligence/symbols.py', name: 'resolve_function_ref', line: 255 }
const widget: PlaygroundWidgetData = {
  kind: 'playground',
  function_ref: fn,
  breadcrumb: 'Step through resolve_function_ref',
  call: { function_ref: fn, args: ['conn', 42, 'ref'] },
  call_text: 'resolve_function_ref(conn, 42, ref)',
}

const trace: StepThroughResponse = {
  kind: 'trace',
  trace: [{ line: 255, event: 'call', changed: ['x'], scope: [{ name: 'x', kind: 'scalar', text: '1' }] }],
  source_lines: [{ num: 255, text: 'def f(x):' }],
  func_name: 'resolve_function_ref', file_line: 'intelligence/symbols.py:255', truncated: false,
}

const truncatedTrace: StepThroughResponse = {
  ...trace,
  truncated: true,
}

const fallback: FallbackResponse = { kind: 'fallback', reason: 'generator', iframe_url: '/playground/abc' }

beforeEach(() => { launchPlayground.mockReset(); closePlayground.mockClear(); _resetForTests() })

describe('PlaygroundWidget — integration (real slot store)', () => {
  // ---- Idle state ----

  it('renders the idle invitation by default', () => {
    render(<PlaygroundWidget widget={widget} onOpenCitation={() => {}} />)
    expect(screen.getByText('intelligence/symbols.py:255')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /step through/i })).toBeInTheDocument()
  })

  // ---- Preview state (deferred concern 1: free-text call) ----

  it('shows the REAL proposed call (not a placeholder) in preview', async () => {
    render(<PlaygroundWidget widget={widget} onOpenCitation={() => {}} />)
    await userEvent.click(screen.getByRole('button', { name: /step through/i }))
    // The real call_text must be visible in the read-only box
    expect(screen.getByText('resolve_function_ref(conn, 42, ref)')).toBeInTheDocument()
    // Never a fake placeholder like "name(…)"
    expect(screen.queryByText('resolve_function_ref(…)')).not.toBeInTheDocument()
  })

  // ---- idle → preview → stepper (deferred concern 1: trace render path) ----

  it('idle → preview → stepper on confirm mounts the React stepper for kind:trace', async () => {
    launchPlayground.mockResolvedValue(trace)
    render(<PlaygroundWidget widget={widget} onOpenCitation={() => {}} />)
    // Step 1: click "Step through" on IdleInvitation → shows PreviewCall
    await userEvent.click(screen.getByRole('button', { name: /step through/i }))
    expect(screen.getByText(/step through this call/i)).toBeInTheDocument()
    // Step 2: confirm in PreviewCall → triggers launch → lands in trace state
    await act(async () => { await userEvent.click(screen.getByRole('button', { name: /^step through$/i })) })
    // Stepper renders the step counter — confirms the trace path is wired
    expect(await screen.findByText('step 1 / 1')).toBeInTheDocument()
  })

  it('stepper renders func_name from the trace response in the head strip', async () => {
    launchPlayground.mockResolvedValue(trace)
    render(<PlaygroundWidget widget={widget} onOpenCitation={() => {}} />)
    await userEvent.click(screen.getByRole('button', { name: /step through/i }))
    await act(async () => { await userEvent.click(screen.getByRole('button', { name: /^step through$/i })) })
    await screen.findByText('step 1 / 1')
    // func_name appears in the Stepper head strip (and breadcrumb)
    expect(screen.getAllByText('resolve_function_ref').length).toBeGreaterThan(0)
  })

  it('stepper renders file_line from the trace response', async () => {
    launchPlayground.mockResolvedValue(trace)
    render(<PlaygroundWidget widget={widget} onOpenCitation={() => {}} />)
    await userEvent.click(screen.getByRole('button', { name: /step through/i }))
    await act(async () => { await userEvent.click(screen.getByRole('button', { name: /^step through$/i })) })
    await screen.findByText('step 1 / 1')
    // file_line appears in the breadcrumb row below the head
    expect(screen.getByText('intelligence/symbols.py:255')).toBeInTheDocument()
  })

  it('stepper renders the step row (scope var x=1)', async () => {
    launchPlayground.mockResolvedValue(trace)
    render(<PlaygroundWidget widget={widget} onOpenCitation={() => {}} />)
    await userEvent.click(screen.getByRole('button', { name: /step through/i }))
    await act(async () => { await userEvent.click(screen.getByRole('button', { name: /^step through$/i })) })
    await screen.findByText('step 1 / 1')
    // The state panel renders the scope var "x" with value "1"
    expect(screen.getByText('x')).toBeInTheDocument()
    expect(screen.getByText('1')).toBeInTheDocument()
  })

  it('stepper renders the × close button', async () => {
    launchPlayground.mockResolvedValue(trace)
    render(<PlaygroundWidget widget={widget} onOpenCitation={() => {}} />)
    await userEvent.click(screen.getByRole('button', { name: /step through/i }))
    await act(async () => { await userEvent.click(screen.getByRole('button', { name: /^step through$/i })) })
    await screen.findByText('step 1 / 1')
    expect(screen.getByRole('button', { name: '×' })).toBeInTheDocument()
  })

  // ---- Truncated badge (deferred concern 2: localized via playground_truncated key) ----

  it('stepper renders the localized truncated badge (en) with step count interpolated', async () => {
    launchPlayground.mockResolvedValue(truncatedTrace)
    render(<PlaygroundWidget widget={widget} onOpenCitation={() => {}} lang="en" />)
    await userEvent.click(screen.getByRole('button', { name: /step through/i }))
    await act(async () => { await userEvent.click(screen.getByRole('button', { name: /^step through$/i })) })
    await screen.findByText('step 1 / 1')
    // The badge uses the playground_truncated key with {n} = total steps (1)
    expect(screen.getByText('Stopped at step 1 — trace truncated.')).toBeInTheDocument()
  })

  it('stepper renders the localized truncated badge in es locale with correct step count', async () => {
    launchPlayground.mockResolvedValue(truncatedTrace)
    render(<PlaygroundWidget widget={widget} onOpenCitation={() => {}} lang="es" />)
    await userEvent.click(screen.getByRole('button', { name: /recorrer/i }))
    await act(async () => { await userEvent.click(screen.getByRole('button', { name: /^recorrer$/i })) })
    await screen.findByText('step 1 / 1')
    // Spanish badge text from playground_truncated es key with {n}=1
    expect(screen.getByText('Detenido en el paso 1 — traza truncada.')).toBeInTheDocument()
  })

  // ---- Free-text override (deferred concern 1: edited call reaches launch) ----

  it('passes the edited free-text call through launch as call_text', async () => {
    launchPlayground.mockResolvedValue(trace)
    render(<PlaygroundWidget widget={widget} onOpenCitation={() => {}} />)
    // Open preview
    await userEvent.click(screen.getByRole('button', { name: /step through/i }))
    // Switch to edit mode
    await userEvent.click(screen.getByRole('button', { name: '✎' }))
    const ta = screen.getByRole('textbox')
    await userEvent.clear(ta)
    await userEvent.type(ta, 'resolve_function_ref(conn, 99, ref)')
    // Confirm — the edited text must flow to launch as call_text
    await act(async () => { await userEvent.click(screen.getByRole('button', { name: /^step through$/i })) })
    expect(launchPlayground).toHaveBeenCalledWith(
      expect.objectContaining({ call_text: 'resolve_function_ref(conn, 99, ref)' }),
    )
  })

  // ---- Fallback branch (deferred concern 1: iframe box) ----

  it('mounts the iframe box for kind:fallback', async () => {
    launchPlayground.mockResolvedValue(fallback)
    const { container } = render(<PlaygroundWidget widget={widget} onOpenCitation={() => {}} />)
    await userEvent.click(screen.getByRole('button', { name: /step through/i }))
    await act(async () => { await userEvent.click(screen.getByRole('button', { name: /^step through$/i })) })
    const iframe = container.querySelector('iframe')
    expect(iframe).toBeTruthy()
    expect(iframe!.getAttribute('src')).toBe('/playground/abc')
  })
})
