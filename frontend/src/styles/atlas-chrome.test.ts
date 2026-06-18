import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'

// Wave 5 deletes styles.css. The Wave-5 survivors (Atlas3DPage, SettingsPage,
// HandoffPage) and the cuaderno-only App shell must render WITHOUT it — every
// class and CSS variable they touch has to live in cuaderno.css + atlas-chrome.css.
//
// The first cut of this guard only checked the BASE classes and tokens used
// INSIDE atlas-chrome.css. That let two real regressions through: HandoffPage
// renders `badge badge-${high|med|low}` and uses var(--accent-cyan-soft), and
// the App shell uses var(--bg) — all three lived ONLY in styles.css. This guard
// now also scans what the survivor .tsx files actually reference, so a green
// test genuinely authorizes the deletion.
const atlas = readFileSync('src/styles/atlas-chrome.css', 'utf8')
const cuaderno = readFileSync('src/styles/cuaderno.css', 'utf8')
const available = atlas + '\n' + cuaderno

// The survivor TSX that renders inside the dark dashboard chrome (not the
// cuaderno paper surface). These are the files at risk when styles.css dies.
const survivors = [
  'src/App.tsx',
  'src/pages/Atlas3DPage.tsx',
  'src/pages/SettingsPage.tsx',
  'src/pages/HandoffPage.tsx',
].map((p) => readFileSync(p, 'utf8'))
const survivorSrc = survivors.join('\n')

const classDefined = (c: string) => new RegExp('\\.' + c + '(?![\\w-])').test(available)
const tokenDefined = (t: string) => new RegExp(t.replace(/[-]/g, '\\-') + '\\s*:').test(available)

describe('Wave-5 survivor chrome is self-contained (no styles.css needed)', () => {
  it('defines the classes Atlas3D / Settings / Handoff use', () => {
    for (const c of [
      'atlas-flow-stage', 'atlas-flow-toolbar', 'atlas-flow-legend',
      'badge', 'panel', 'page-header', 'section-title', 'insight-card',
      // HandoffPage builds `badge badge-${high|med|low}` dynamically.
      'badge-high', 'badge-med', 'badge-low',
    ]) {
      expect(classDefined(c), `.${c} missing`).toBe(true)
    }
  })

  it('leaves no dangling CSS variable inside atlas-chrome.css', () => {
    const used = [...atlas.matchAll(/var\((--[a-z0-9-]+)/g)].map((m) => m[1])
    const missing = [...new Set(used)].filter((t) => !tokenDefined(t))
    expect(missing, `undefined tokens after styles.css deletion: ${missing}`).toEqual([])
  })

  it('defines every CSS variable the survivor .tsx files reference', () => {
    const used = [...survivorSrc.matchAll(/var\((--[a-z0-9-]+)/g)].map((m) => m[1])
    const missing = [...new Set(used)].filter((t) => !tokenDefined(t))
    expect(missing, `tokens used by survivors but undefined after styles.css deletion: ${missing}`).toEqual([])
  })
})
