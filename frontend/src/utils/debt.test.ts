import { describe, it, expect } from 'vitest'
import { scoreToBand, relativeBand } from './debt'

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

// The live debt distribution is compressed (e.g. 29-74, all "high"/"medium" in
// absolute terms), so bands must be RELATIVE to the shown range: the hottest
// node paints brightest regardless of absolute value.
describe('relativeBand', () => {
  it('spreads a compressed range across the full ramp', () => {
    const [min, max] = [50, 60]
    expect(relativeBand(60, min, max)).toBe('critical')
    expect(relativeBand(57, min, max)).toBe('high')
    expect(relativeBand(53, min, max)).toBe('medium')
    expect(relativeBand(50, min, max)).toBe('low')
  })
  it('avoids a false hotspot when there is no spread', () => {
    expect(relativeBand(50, 50, 50)).toBe('medium')
  })
})
