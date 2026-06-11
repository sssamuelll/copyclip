// Wave 5 collapsed the surface to the cuaderno. The three surviving auxiliary
// views are reached from the cuaderno's ⊞ menu (not a persistent sidebar) and
// render full-screen with a "back to cuaderno" control.
export type SurvivorPage = 'atlas-3d' | 'handoff' | 'settings'

export const SURVIVOR_NAV: { id: SurvivorPage; label: string }[] = [
  { id: 'atlas-3d', label: 'codebase map' },
  { id: 'handoff', label: 'safe handoff' },
  { id: 'settings', label: 'settings' },
]

export const SURVIVOR_LABELS: Record<SurvivorPage, string> = Object.fromEntries(
  SURVIVOR_NAV.map((s) => [s.id, s.label]),
) as Record<SurvivorPage, string>
