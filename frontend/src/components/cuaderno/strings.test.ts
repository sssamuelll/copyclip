import { describe, it, expect } from 'vitest'
import { t } from './strings'

describe('step-through strings', () => {
  it('returns the breadcrumb verb per language', () => {
    expect(t('playground_step_through', 'en')).toBe('Step through')
    expect(t('playground_step_through', 'es')).toBe('Recorrer')
  })
  it('falls back to en for an unknown lang', () => {
    expect(t('playground_truncated', null, { n: '42' })).toBe('Stopped at step 42 — trace truncated.')
  })

  describe('interpolation', () => {
    it('substitutes {n} in playground_truncated (en)', () => {
      expect(t('playground_truncated', 'en', { n: '7' })).toBe('Stopped at step 7 — trace truncated.')
    })
    it('substitutes {n} in playground_truncated (es)', () => {
      expect(t('playground_truncated', 'es', { n: '3' })).toBe('Detenido en el paso 3 — traza truncada.')
    })
    it('substitutes {reason} in playground_fallback_note (en)', () => {
      expect(t('playground_fallback_note', 'en', { reason: 'it uses *args' })).toBe(
        "This function can't be stepped through yet — it uses *args. Here's its input and output.",
      )
    })
    it('substitutes {reason} in playground_fallback_note (es)', () => {
      expect(t('playground_fallback_note', 'es', { reason: 'usa *args' })).toBe(
        'Esta función no se puede recorrer paso a paso todavía — usa *args. Aquí está su entrada y salida.',
      )
    })
    it('leaves unmatched placeholders untouched when no params supplied', () => {
      // Callers that do not pass params get the template back, not an exception.
      expect(t('playground_truncated', 'en')).toBe('Stopped at step {n} — trace truncated.')
    })
    it('leaves unmatched placeholders untouched when only partial params supplied', () => {
      expect(t('playground_fallback_note', 'en', {})).toBe(
        "This function can't be stepped through yet — {reason}. Here's its input and output.",
      )
    })
  })
})
