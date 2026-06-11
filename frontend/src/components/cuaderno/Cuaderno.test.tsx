import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { Cuaderno } from './Cuaderno'

// Wave 5 / D1: the grouped dashboard sidebar is gone. The cuaderno is the only
// surface; its ⊞ control opens a small menu to the three survivor views and
// navigates to the chosen one. No ⊞ menu without an onNavigate handler.
const baseProps = {
  sessionLabel: 'session abcd',
  questionNumber: '01 · q',
  questions: [],
  activeQuestion: null,
  isLoading: false,
  onAsk: () => {},
  onSelectFromHistory: () => {},
  onSetGotIt: () => {},
}

describe('Cuaderno ⊞ survivor menu', () => {
  it('opens the menu and navigates to a survivor surface', () => {
    const onNavigate = vi.fn()
    render(<Cuaderno {...baseProps} onNavigate={onNavigate} />)

    // The menu is closed until ⊞ is clicked.
    expect(screen.queryByText('safe handoff')).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: /surfaces/i }))
    fireEvent.click(screen.getByText('safe handoff'))

    expect(onNavigate).toHaveBeenCalledWith('handoff')
    // Selecting closes the menu.
    expect(screen.queryByText('safe handoff')).toBeNull()
  })

  it('shows no ⊞ control when navigation is unavailable', () => {
    render(<Cuaderno {...baseProps} />)
    expect(screen.queryByRole('button', { name: /surfaces/i })).toBeNull()
  })
})
