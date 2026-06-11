import { describe, it, expect } from 'vitest'
import { scoreToBand } from './debt'

// Bands mirror the backend's canonical SEVERITY_BUCKETS (critical 75 / high 50 /
// medium 25 / low 0) so the cyan the user sees matches the computed severity.
describe('scoreToBand', () => {
  it('maps the canonical buckets at their boundaries', () => {
    expect(scoreToBand(90)).toBe('critical')
    expect(scoreToBand(75)).toBe('critical')
    expect(scoreToBand(74.9)).toBe('high')
    expect(scoreToBand(50)).toBe('high')
    expect(scoreToBand(49)).toBe('medium')
    expect(scoreToBand(25)).toBe('medium')
    expect(scoreToBand(24)).toBe('low')
    expect(scoreToBand(0)).toBe('low')
  })
})
