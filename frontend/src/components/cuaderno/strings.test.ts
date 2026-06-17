import { describe, it, expect } from 'vitest'
import { t } from './strings'

describe('step-through strings', () => {
  it('returns the breadcrumb verb per language', () => {
    expect(t('playground_step_through', 'en')).toBe('Step through')
    expect(t('playground_step_through', 'es')).toBe('Recorrer')
  })
  it('falls back to en for an unknown lang', () => {
    expect(t('playground_truncated', null)).toBe('Stopped at step {n} — trace truncated.')
  })
})
