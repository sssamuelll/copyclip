import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import { mkRow } from './trace'
import { StateRow } from './StateRow'

describe('StateRow', () => {
  it('renders a scalar value as text', () => {
    const row = mkRow('module_id', { kind: 'scalar', text: '42' }, true, 0, {})
    render(<StateRow row={row} onToggle={() => {}} />)
    expect(screen.getByText('42')).toBeInTheDocument()
    expect(screen.getByText('module_id')).toBeInTheDocument()
  })
  it('wraps an opaque label in angle quotes', () => {
    const row = mkRow('conn', { kind: 'opaque', label: 'Connection' }, false, 0, {})
    render(<StateRow row={row} onToggle={() => {}} />)
    expect(screen.getByText('‹Connection›')).toBeInTheDocument()
  })
  it('renders a large chip with summary + meta + caret and fires onToggle', async () => {
    const row = mkRow('ref', { kind: 'large', summary: 'FunctionRef', meta: '5 fields' }, true, 0, {})
    const onToggle = vi.fn()
    render(<StateRow row={row} onToggle={onToggle} />)
    expect(screen.getByText('FunctionRef')).toBeInTheDocument()
    expect(screen.getByText('5 fields')).toBeInTheDocument()
    await userEvent.click(screen.getByText('FunctionRef'))
    expect(onToggle).toHaveBeenCalledWith('ref')
  })
  it('does not make non-large rows clickable', async () => {
    const row = mkRow('x', { kind: 'object', text: "Symbol('Foo')" }, false, 0, {})
    const onToggle = vi.fn()
    render(<StateRow row={row} onToggle={onToggle} />)
    await userEvent.click(screen.getByText("Symbol('Foo')"))
    expect(onToggle).not.toHaveBeenCalled()
  })
})
