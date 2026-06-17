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
  it('confirms the UNEDITED proposed call when not edited', async () => {
    const onConfirm = vi.fn()
    render(<PreviewCall funcName="f" initialCall="f(1)" onConfirm={onConfirm} onCancel={() => {}} />)
    await userEvent.click(screen.getByRole('button', { name: /^step through$/i }))
    expect(onConfirm).toHaveBeenCalledWith('f(1)')
  })
  it('reveals a textarea when editing and confirms the edited free-text call', async () => {
    const onConfirm = vi.fn()
    render(<PreviewCall funcName="f" initialCall="f(1)" onConfirm={onConfirm} onCancel={() => {}} />)
    await userEvent.click(screen.getByRole('button', { name: '✎' }))
    const ta = screen.getByRole('textbox')
    await userEvent.clear(ta)
    await userEvent.type(ta, 'f(2)')
    await userEvent.click(screen.getByRole('button', { name: /^step through$/i }))
    expect(onConfirm).toHaveBeenCalledWith('f(2)')
  })
  it('fires onCancel', async () => {
    const onCancel = vi.fn()
    render(<PreviewCall funcName="f" initialCall="f(1)" onConfirm={() => {}} onCancel={onCancel} />)
    await userEvent.click(screen.getByRole('button', { name: /cancel/i }))
    expect(onCancel).toHaveBeenCalled()
  })
})
