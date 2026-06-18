import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

// Wave 5 / D1: the dashboard shell is gone. The cuaderno is the only home; its
// ⊞ menu navigates to a survivor, which renders full-screen with a "back to
// cuaderno" control. Pages are stubbed so this tests the App shell wiring only.
vi.mock('./pages/CuadernoPage', () => ({
  CuadernoPage: ({ onNavigate }: { onNavigate?: (t: string) => void }) => (
    <div>
      <div>cuaderno-home</div>
      <button onClick={() => onNavigate?.('settings')}>go-settings</button>
    </div>
  ),
}))
vi.mock('./pages/SettingsPage', () => ({ SettingsPage: () => <div>settings-survivor</div> }))
vi.mock('./pages/Atlas3DPage', () => ({ Atlas3DPage: () => <div>atlas-survivor</div> }))
vi.mock('./pages/HandoffPage', () => ({ HandoffPage: () => <div>handoff-survivor</div> }))

import { App } from './App'

describe('App cuaderno-only navigation', () => {
  it('opens a survivor full-screen and returns to the cuaderno', () => {
    render(<App />)
    expect(screen.getByText('cuaderno-home')).toBeTruthy()

    fireEvent.click(screen.getByText('go-settings'))
    expect(screen.getByText('settings-survivor')).toBeTruthy()
    expect(screen.queryByText('cuaderno-home')).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: /cuaderno/i }))
    expect(screen.getByText('cuaderno-home')).toBeTruthy()
    expect(screen.queryByText('settings-survivor')).toBeNull()
  })
})
