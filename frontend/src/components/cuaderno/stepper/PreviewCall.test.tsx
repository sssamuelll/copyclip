import { render, screen } from '@testing-library/react'
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
})
