import { render, screen, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import { PreviewCall } from './PreviewCall'

describe('PreviewCall', () => {
  it('shows the proposed call read-only with a pencil button', () => {
    render(<PreviewCall funcName="resolve_function_ref" initialCall="resolve_function_ref(conn, 42, ref)" onConfirm={() => {}} onCancel={() => {}} />)
    expect(screen.getByText('resolve_function_ref(conn, 42, ref)')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '✎' })).toBeInTheDocument()
  })

  // ---- needs_args affordance ----

  it('needs_args=true: renders the complete-call hint and an editable textarea (no read-only box)', () => {
    render(
      <PreviewCall
        funcName="needs_arg"
        initialCall="needs_arg()"
        onConfirm={() => {}}
        onCancel={() => {}}
        needsArgs={true}
        lang="en"
      />
    )
    // Hint must be present
    expect(screen.getByTestId('needs-args-hint')).toBeInTheDocument()
    expect(screen.getByText("Complete the call's arguments before stepping through.")).toBeInTheDocument()
    // Textarea must be directly visible (no pencil click required)
    expect(screen.getByRole('textbox')).toBeInTheDocument()
    // The read-only div + pencil should NOT be present (we are already in edit mode)
    expect(screen.queryByRole('button', { name: '✎' })).toBeNull()
    // The "Edit call" toggle button should not be present for needs_args widgets
    expect(screen.queryByRole('button', { name: /edit call/i })).toBeNull()
  })

  it('needs_args=true (es): renders the Spanish hint text', () => {
    render(
      <PreviewCall
        funcName="needs_arg"
        initialCall="needs_arg()"
        onConfirm={() => {}}
        onCancel={() => {}}
        needsArgs={true}
        lang="es"
      />
    )
    expect(screen.getByTestId('needs-args-hint')).toBeInTheDocument()
    expect(screen.getByText('Completa los argumentos de la llamada antes de recorrer.')).toBeInTheDocument()
  })

  it('needs_args=false (normal widget): NO hint rendered', () => {
    render(
      <PreviewCall
        funcName="f"
        initialCall="f(1, 2)"
        onConfirm={() => {}}
        onCancel={() => {}}
        needsArgs={false}
        lang="en"
      />
    )
    expect(screen.queryByTestId('needs-args-hint')).toBeNull()
    expect(screen.queryByText("Complete the call's arguments before stepping through.")).toBeNull()
    // Normal path: read-only display with pencil
    expect(screen.getByRole('button', { name: '✎' })).toBeInTheDocument()
  })

  it('needs_args absent (normal widget): NO hint rendered', () => {
    render(
      <PreviewCall
        funcName="f"
        initialCall="f(1)"
        onConfirm={() => {}}
        onCancel={() => {}}
        lang="en"
      />
    )
    expect(screen.queryByTestId('needs-args-hint')).toBeNull()
    // Normal path: read-only display with pencil
    expect(screen.getByRole('button', { name: '✎' })).toBeInTheDocument()
  })

  it('needs_args=true: confirm sends dirty=true because the textarea starts editable (user must change it)', async () => {
    const onConfirm = vi.fn()
    render(
      <PreviewCall
        funcName="needs_arg"
        initialCall="needs_arg()"
        onConfirm={onConfirm}
        onCancel={() => {}}
        needsArgs={true}
        lang="en"
      />
    )
    const ta = screen.getByRole('textbox')
    await userEvent.clear(ta)
    await userEvent.type(ta, 'needs_arg(42)')
    await userEvent.click(screen.getByRole('button', { name: /^step through$/i }))
    expect(onConfirm).toHaveBeenCalledWith('needs_arg(42)', true)
  })
  it('confirms the UNEDITED proposed call when not edited', async () => {
    const onConfirm = vi.fn()
    render(<PreviewCall funcName="f" initialCall="f(1)" onConfirm={onConfirm} onCancel={() => {}} />)
    await userEvent.click(screen.getByRole('button', { name: /^step through$/i }))
    expect(onConfirm).toHaveBeenCalledWith('f(1)', false)
  })
  it('reveals a textarea when editing and confirms the edited free-text call', async () => {
    const onConfirm = vi.fn()
    render(<PreviewCall funcName="f" initialCall="f(1)" onConfirm={onConfirm} onCancel={() => {}} />)
    await userEvent.click(screen.getByRole('button', { name: '✎' }))
    const ta = screen.getByRole('textbox')
    await userEvent.clear(ta)
    await userEvent.type(ta, 'f(2)')
    await userEvent.click(screen.getByRole('button', { name: /^step through$/i }))
    expect(onConfirm).toHaveBeenCalledWith('f(2)', true)
  })
  it('fires onCancel', async () => {
    const onCancel = vi.fn()
    render(<PreviewCall funcName="f" initialCall="f(1)" onConfirm={() => {}} onCancel={onCancel} />)
    await userEvent.click(screen.getByRole('button', { name: /cancel/i }))
    expect(onCancel).toHaveBeenCalled()
  })

  it('onConfirm receives dirty=false when user never edited the textarea', async () => {
    const onConfirm = vi.fn()
    render(<PreviewCall funcName="f" initialCall="f(1)" onConfirm={onConfirm} onCancel={() => {}} />)
    await userEvent.click(screen.getByRole('button', { name: /^step through$/i }))
    expect(onConfirm).toHaveBeenCalledWith('f(1)', false)
  })

  it('onConfirm receives dirty=true when user edited the textarea', async () => {
    const onConfirm = vi.fn()
    render(<PreviewCall funcName="f" initialCall="f(1)" onConfirm={onConfirm} onCancel={() => {}} />)
    await userEvent.click(screen.getByRole('button', { name: '✎' }))
    const ta = screen.getByRole('textbox')
    await userEvent.clear(ta)
    await userEvent.type(ta, 'f(2)')
    await userEvent.click(screen.getByRole('button', { name: /^step through$/i }))
    expect(onConfirm).toHaveBeenCalledWith('f(2)', true)
  })

  // ---- FIX 1: gate the confirm for needs_args (cannot step through a bare template) ----

  it('needs_args=true with bare template: Step-through button is DISABLED and clicking does not fire onConfirm', async () => {
    const onConfirm = vi.fn()
    render(
      <PreviewCall
        funcName="f"
        initialCall="f()"
        onConfirm={onConfirm}
        onCancel={() => {}}
        needsArgs={true}
        lang="en"
      />
    )
    const step = screen.getByRole('button', { name: /^step through$/i })
    // Button must be visibly disabled while the call is still the bare template
    expect(step).toBeDisabled()
    // Clicking the disabled button must NOT fire onConfirm
    await userEvent.click(step)
    expect(onConfirm).not.toHaveBeenCalled()
  })

  it('needs_args=true: editing the textarea away from the bare template enables Step-through and clicking fires onConfirm(dirty=true)', async () => {
    const onConfirm = vi.fn()
    render(
      <PreviewCall
        funcName="f"
        initialCall="f()"
        onConfirm={onConfirm}
        onCancel={() => {}}
        needsArgs={true}
        lang="en"
      />
    )
    const ta = screen.getByRole('textbox')
    // Simulate a change event that supplies arguments
    fireEvent.change(ta, { target: { value: "f('x')" } })
    const step = screen.getByRole('button', { name: /^step through$/i })
    expect(step).toBeEnabled()
    await userEvent.click(step)
    expect(onConfirm).toHaveBeenCalledWith("f('x')", true)
  })

  it('needs_args=true: typing then clearing back to the bare template re-disables Step-through', async () => {
    const onConfirm = vi.fn()
    render(
      <PreviewCall
        funcName="f"
        initialCall="f()"
        onConfirm={onConfirm}
        onCancel={() => {}}
        needsArgs={true}
        lang="en"
      />
    )
    const ta = screen.getByRole('textbox')
    fireEvent.change(ta, { target: { value: "f('x')" } })
    expect(screen.getByRole('button', { name: /^step through$/i })).toBeEnabled()
    // Back to the bare template (with surrounding whitespace, still incomplete)
    fireEvent.change(ta, { target: { value: '  f()  ' } })
    expect(screen.getByRole('button', { name: /^step through$/i })).toBeDisabled()
  })

  it('non-needsArgs PreviewCall: Step-through button is enabled from the start', () => {
    render(<PreviewCall funcName="f" initialCall="f(1)" onConfirm={() => {}} onCancel={() => {}} />)
    expect(screen.getByRole('button', { name: /^step through$/i })).toBeEnabled()
  })

  // ---- arg_source provenance chip ----

  it('renders the tests-provenance chip (en) when argSource="tests"', () => {
    render(
      <PreviewCall
        funcName="target"
        initialCall="target('abc')"
        onConfirm={() => {}}
        onCancel={() => {}}
        argSource="tests"
        lang="en"
      />
    )
    const chip = screen.getByTestId('arg-source-chip')
    expect(chip).toHaveTextContent('from a test')
  })

  it('renders the tests-provenance chip (es, Venezuelan tuteo)', () => {
    render(
      <PreviewCall
        funcName="target"
        initialCall="target('abc')"
        onConfirm={() => {}}
        onCancel={() => {}}
        argSource="tests"
        lang="es"
      />
    )
    expect(screen.getByTestId('arg-source-chip')).toHaveTextContent('args de un test')
  })

  it('renders the manual chip when argSource="manual"', () => {
    render(
      <PreviewCall
        funcName="needs_arg"
        initialCall="needs_arg()"
        onConfirm={() => {}}
        onCancel={() => {}}
        needsArgs={true}
        argSource="manual"
        lang="es"
      />
    )
    expect(screen.getByTestId('arg-source-chip')).toHaveTextContent('completa la llamada')
  })

  it('renders no chip when argSource is absent', () => {
    render(<PreviewCall funcName="f" initialCall="f(1)" onConfirm={() => {}} onCancel={() => {}} />)
    expect(screen.queryByTestId('arg-source-chip')).toBeNull()
  })
})
