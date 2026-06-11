import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'

// W4-4 / decision D: the chrome the Wave-5 survivors (Atlas3DPage, SettingsPage,
// HandoffPage) use must live OUTSIDE styles.css, so Wave 5 can delete it. The
// survivor styles now live in cuaderno.css + atlas-chrome.css; this proves they
// are self-contained — classes defined AND no CSS variable left dangling.
const atlas = readFileSync('src/styles/atlas-chrome.css', 'utf8')
const cuaderno = readFileSync('src/styles/cuaderno.css', 'utf8')
const available = atlas + '\n' + cuaderno

describe('Wave-5 survivor chrome is self-contained (no styles.css needed)', () => {
  it('defines the classes Atlas3D / Settings use', () => {
    for (const c of [
      'atlas-flow-stage', 'atlas-flow-toolbar', 'atlas-flow-legend',
      'badge', 'panel', 'page-header', 'section-title', 'insight-card',
    ]) {
      expect(new RegExp('\\.' + c + '(?![\\w-])').test(available), `.${c} missing`).toBe(true)
    }
  })

  it('leaves no dangling CSS variable (every var() it uses is defined here)', () => {
    const used = [...atlas.matchAll(/var\((--[a-z0-9-]+)/g)].map((m) => m[1])
    const missing = [...new Set(used)].filter((t) => !new RegExp(t + '\\s*:').test(available))
    expect(missing, `undefined tokens after styles.css deletion: ${missing}`).toEqual([])
  })
})
