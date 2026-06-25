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

const fallback: FallbackResponse = { kind: 'fallback', reason: 'generator', iframe_url: '/playground/abc', playground_id: 'abc' }
const fallbackWithReason: FallbackResponse = { kind: 'fallback', reason: 'async function — nothing to step through', iframe_url: 'http://127.0.0.1:5000/', playground_id: 'pg-abc123' }

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
      expect.any(AbortSignal),
    )
  })

  // ---- Dirty-flag consent-path (PR #177 must-fix #1) ----

  it('unedited confirm sends call descriptor WITHOUT call_text (structured path)', async () => {
    launchPlayground.mockResolvedValue(trace)
    render(<PlaygroundWidget widget={widget} onOpenCitation={() => {}} />)
    await userEvent.click(screen.getByRole('button', { name: /step through/i }))
    // Confirm WITHOUT editing — dirty=false, so call_text must be absent
    await act(async () => { await userEvent.click(screen.getByRole('button', { name: /^step through$/i })) })
    expect(launchPlayground).toHaveBeenCalledWith(
      expect.objectContaining({ call: widget.call }),
      expect.any(AbortSignal),
    )
    // call_text must NOT be present when unedited
    const callArg = launchPlayground.mock.calls[0][0]
    expect(callArg).not.toHaveProperty('call_text')
  })

  it('edited confirm sends call_text (free-text path)', async () => {
    launchPlayground.mockResolvedValue(trace)
    render(<PlaygroundWidget widget={widget} onOpenCitation={() => {}} />)
    await userEvent.click(screen.getByRole('button', { name: /step through/i }))
    await userEvent.click(screen.getByRole('button', { name: '✎' }))
    const ta = screen.getByRole('textbox')
    await userEvent.clear(ta)
    await userEvent.type(ta, 'resolve_function_ref(conn, 0, ref)')
    await act(async () => { await userEvent.click(screen.getByRole('button', { name: /^step through$/i })) })
    expect(launchPlayground).toHaveBeenCalledWith(
      expect.objectContaining({ call_text: 'resolve_function_ref(conn, 0, ref)' }),
      expect.any(AbortSignal),
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

  // ---- Fallback reason note (Critical #3 + High #5) ----

  it('renders playground_fallback_note (en) above the iframe when kind:fallback has a reason', async () => {
    launchPlayground.mockResolvedValue(fallbackWithReason)
    render(<PlaygroundWidget widget={widget} onOpenCitation={() => {}} lang="en" />)
    await userEvent.click(screen.getByRole('button', { name: /step through/i }))
    await act(async () => { await userEvent.click(screen.getByRole('button', { name: /^step through$/i })) })
    // The fallback note is the localized string with {reason} interpolated
    expect(await screen.findByText(/async function — nothing to step through/)).toBeInTheDocument()
    // Full note text
    expect(screen.getByText("This function can't be stepped through yet — async function — nothing to step through. Here's its input and output.")).toBeInTheDocument()
  })

  it('renders playground_fallback_note (es) with the reason interpolated', async () => {
    launchPlayground.mockResolvedValue(fallbackWithReason)
    render(<PlaygroundWidget widget={widget} onOpenCitation={() => {}} lang="es" />)
    await userEvent.click(screen.getByRole('button', { name: /recorrer/i }))
    await act(async () => { await userEvent.click(screen.getByRole('button', { name: /^recorrer$/i })) })
    expect(await screen.findByText(/async function — nothing to step through/)).toBeInTheDocument()
    expect(screen.getByText('Esta función no se puede recorrer paso a paso todavía — async function — nothing to step through. Aquí está su entrada y salida.')).toBeInTheDocument()
  })

  // ---- Empty trace guard (Critical #2) ----

  it('shows nothing_ran message (not an empty Stepper) when kind:trace has trace:[]', async () => {
    launchPlayground.mockResolvedValue({ kind: 'trace', trace: [], source_lines: [], func_name: 'resolve_function_ref', file_line: 'intelligence/symbols.py:255', truncated: false })
    render(<PlaygroundWidget widget={widget} onOpenCitation={() => {}} />)
    await userEvent.click(screen.getByRole('button', { name: /step through/i }))
    await act(async () => { await userEvent.click(screen.getByRole('button', { name: /^step through$/i })) })
    // Must NOT render a step counter (would mean Stepper was mounted on empty trace)
    expect(screen.queryByText(/step \d+ \/ \d+/)).toBeNull()
    // Must render the nothing-ran message (server-derived from func_name)
    expect(await screen.findByText(/did not enter this function/)).toBeInTheDocument()
  })

  // ---- Honest bare fallback when call_text absent (SHOULD — callTextOf deleted) ----
  // proposedCall = widget.call_text ?? fn.name + '()'
  // When call_text is absent, the preview shows fn.name + '()' — no repr generation.

  it('shows bare fn.name() when call_text is absent (honest fallback, no repr generation)', async () => {
    const widgetNoCallText: typeof widget = {
      ...widget,
      call_text: undefined,
      call: { function_ref: fn, args: ['hello', 42] },
    }
    render(<PlaygroundWidget widget={widgetNoCallText} onOpenCitation={() => {}} />)
    await userEvent.click(screen.getByRole('button', { name: /step through/i }))
    // Bare fallback: fn.name + '()'
    expect(screen.getByText('resolve_function_ref()')).toBeInTheDocument()
  })

  it('shows widget.call_text when present, ignoring call descriptor', async () => {
    render(<PlaygroundWidget widget={widget} onOpenCitation={() => {}} />)
    await userEvent.click(screen.getByRole('button', { name: /step through/i }))
    // call_text takes priority
    expect(screen.getByText('resolve_function_ref(conn, 42, ref)')).toBeInTheDocument()
  })

  it('bare fallback when call_text absent and ctor present (no Ctor.method rendering)', async () => {
    const fnWithQualname = { ...fn, qualname: 'MyClass.resolve_function_ref' }
    const widgetWithCtor: typeof widget = {
      ...widget,
      call_text: undefined,
      call: {
        function_ref: fnWithQualname,
        args: [42],
        ctor: { args: ['db'] },
      },
    }
    render(<PlaygroundWidget widget={widgetWithCtor} onOpenCitation={() => {}} />)
    await userEvent.click(screen.getByRole('button', { name: /step through/i }))
    // Honest bare fallback: fn.name + '()' — no ctor rendering
    expect(screen.getByText('resolve_function_ref()')).toBeInTheDocument()
  })
})
