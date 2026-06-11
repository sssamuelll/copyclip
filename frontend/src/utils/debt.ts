import type { DebtSeverity } from '../types/api'

export type FogLevel = 'low' | 'med' | 'high'
export type FogClass = 'fog-critical' | 'fog-high' | 'fog-med' | 'fog-low'

export function fogToSeverity(level: FogLevel | string | undefined | null): DebtSeverity {
  if (level === 'high') return 'high'
  if (level === 'med') return 'medium'
  return 'low'
}

// Map a 0-100 cognitive_debt_score to a severity band. Mirrors the backend's
// canonical SEVERITY_BUCKETS (critical 75 / high 50 / medium 25 / low) so the
// cyan a node is painted matches the computed severity — quantized into legible
// bands, never a smooth ramp.
export function scoreToBand(score: number): DebtSeverity {
  if (score >= 75) return 'critical'
  if (score >= 50) return 'high'
  if (score >= 25) return 'medium'
  return 'low'
}

export function fogClass(input: { severity?: DebtSeverity | string; fog_level?: FogLevel | string }): FogClass {
  const sev = input.severity ?? fogToSeverity(input.fog_level)
  if (sev === 'critical') return 'fog-critical'
  if (sev === 'high') return 'fog-high'
  if (sev === 'medium') return 'fog-med'
  return 'fog-low'
}

export function fogFill(input: { severity?: DebtSeverity | string; fog_level?: FogLevel | string }): string {
  const cls = fogClass(input)
  const pct = cls === 'fog-critical' ? 60 : cls === 'fog-high' ? 40 : cls === 'fog-med' ? 22 : 10
  return `color-mix(in srgb, var(--accent-cyan) ${pct}%, transparent)`
}

export function fogBorder(input: { severity?: DebtSeverity | string; fog_level?: FogLevel | string }): string {
  const cls = fogClass(input)
  if (cls === 'fog-critical' || cls === 'fog-high') return 'var(--accent-cyan)'
  if (cls === 'fog-med') return 'color-mix(in srgb, var(--accent-cyan) 50%, var(--text-secondary))'
  return 'var(--border)'
}
