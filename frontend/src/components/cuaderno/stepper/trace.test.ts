import { describe, it, expect } from 'vitest'
import type { Step, Var, Junction } from '../../../types/api'
import { clampStep, nextChange, trackFraction, lineModels, buildRows, markerLefts, sourceTranslateY, ROW_H, junctionOverlay } from './trace'

const v = (name: string, kind: Var['kind'], extra: Partial<Var> = {}): Var => ({ name, kind, ...extra })

// resolveTrace happy path (handoff 742–750): 9 steps, line 263 skipped.
const TRACE: Step[] = [
  { line: 255, event: 'call', changed: ['conn', 'module_id', 'ref'], scope: [v('conn', 'opaque', { label: 'Connection' }), v('module_id', 'scalar', { text: '42' }), v('ref', 'large', { summary: 'FunctionRef', meta: '5 fields', children: [{ name: 'qualname', text: "'Foo.method'" }, { name: 'file', text: "'symbols.py'" }] })] },
  { line: 256, event: 'line', changed: ['qualname'], scope: [v('qualname', 'scalar', { text: "'Foo.method'" })] },
  { line: 257, event: 'line', changed: ['parent'], scope: [v('parent', 'scalar', { text: 'None' })] },
  { line: 258, event: 'line', changed: [], scope: [v('qualname', 'scalar', { text: "'Foo.method'" })] },
  { line: 259, event: 'line', changed: ['head', 'tail'], scope: [v('head', 'scalar', { text: "'Foo'" }), v('tail', 'scalar', { text: "'method'" })] },
  { line: 260, event: 'line', changed: ['parent'], scope: [v('parent', 'object', { text: "Symbol('Foo')" })] },
  { line: 261, event: 'line', changed: ['row'], scope: [v('row', 'large', { summary: 'dict', meta: '5 keys', children: [{ name: 'id', text: '91' }] })] },
  { line: 262, event: 'line', changed: [], scope: [v('row', 'large', { summary: 'dict', meta: '5 keys' })] },
  { line: 264, event: 'return', changed: ['return'], scope: [v('return', 'object', { text: "Symbol('Foo.method')" })] },
]
const SRC = [255, 256, 257, 258, 259, 260, 261, 262, 263, 264].map((num) => ({ num, text: `line ${num}` }))

describe('clampStep', () => {
  it('is 1-based and clamps to [1, len]', () => {
    expect(clampStep(0, 9)).toBe(1)
    expect(clampStep(5, 9)).toBe(5)
    expect(clampStep(99, 9)).toBe(9)
  })
})

describe('nextChange', () => {
  it('wraps modulo length, never lands on the current step', () => {
    // step 9 (return) -> next change wraps to step 1 (call)
    expect(nextChange(9, TRACE)).toBe(1)
  })
  it('skips no-change steps (258 has changed=[])', () => {
    // step 3 (line 257) -> step 5 (line 259), skipping step 4 (258, no change)
    expect(nextChange(3, TRACE)).toBe(5)
  })
  it('returns current step (no infinite loop) when ALL steps have empty changed arrays', () => {
    // Trace where every step has changed:[] — nextChange must terminate and return cur
    const allEmpty: Step[] = [
      { line: 1, event: 'call',   changed: [], scope: [] },
      { line: 2, event: 'line',   changed: [], scope: [] },
      { line: 3, event: 'return', changed: [], scope: [] },
    ]
    expect(nextChange(1, allEmpty)).toBe(1)
    expect(nextChange(2, allEmpty)).toBe(2)
    expect(nextChange(3, allEmpty)).toBe(3)
  })
})

describe('trackFraction', () => {
  it('maps a click fraction to a 1-based clamped step', () => {
    expect(trackFraction(0, 9)).toBe(1)
    expect(trackFraction(1, 9)).toBe(9)
    expect(trackFraction(0.5, 9)).toBe(5) // round(0.5*8)+1 = 5
  })
})

describe('lineModels', () => {
  it('marks the current source index with accent-ink + weight 700', () => {
    const models = lineModels(SRC, 0)
    expect(models[0].numStyle).toContain('var(--accent-ink)')
    expect(models[0].numStyle).toContain('font-weight:700')
    expect(models[1].numStyle).toContain('var(--ink-4)')
    expect(models[1].codeStyle).toContain('var(--ink-2)')
  })
  it('marks NO line when curIdx < 0 (stale anchor, spec §7)', () => {
    const models = lineModels(SRC, -1)
    models.forEach((m) => {
      expect(m.numStyle).toContain('var(--ink-4)')
      expect(m.numStyle).not.toContain('var(--accent-ink)')
    })
  })
})

describe('buildRows', () => {
  it('renders every scope var; only changed names get accent + visible diamond', () => {
    const rows = buildRows(TRACE[0], {})
    expect(rows.map((r) => r.name)).toEqual(['conn', 'module_id', 'ref'])
    expect(rows[1].dotStyle).toContain('opacity:1')      // module_id changed
    expect(rows[1].scalarStyle).toContain('var(--accent-ink)')
  })
  it('an unchanged var keeps the diamond in the DOM at opacity 0 (no reflow)', () => {
    const rows = buildRows(TRACE[3], {})  // changed=[]
    expect(rows[0].dotStyle).toContain('opacity:0')
  })
  it('expands a large var into non-changed scalar children at indent 1', () => {
    const rows = buildRows(TRACE[0], { ref: true })
    const names = rows.map((r) => r.name)
    expect(names).toEqual(['conn', 'module_id', 'ref', 'qualname', 'file'])
    const child = rows.find((r) => r.name === 'qualname')!
    expect(child.isScalar).toBe(true)
    expect(child.scalarStyle).toContain('var(--ink-3)') // forced changed:false
    expect(child.rowStyle).toContain('3.5px 0 3.5px 20px') // indent 1
  })
  it('opaque vars never reflect changed and render a label', () => {
    const rows = buildRows(TRACE[0], {})
    expect(rows[0].isOpaque).toBe(true)
    expect(rows[0].label).toBe('Connection')
  })
})

describe('sourceTranslateY (source column scroll)', () => {
  const VIS = 10 * ROW_H // 260px — 10 visible rows

  it('returns 0 when all lines fit in the visible area', () => {
    expect(sourceTranslateY(5, 8, VIS)).toBe(0)
  })

  it('returns 0 when curIdx < 0 (stale anchor)', () => {
    expect(sourceTranslateY(-1, 30, VIS)).toBe(0)
  })

  it('returns 0 for the first line of a long source', () => {
    // curIdx=0: ideal centres line 0. With clamping it cannot go positive → 0.
    expect(sourceTranslateY(0, 25, VIS)).toBe(0)
  })

  it('scrolls so a late line in a >20-line source stays within the visible region', () => {
    // 25-line source (25*ROW_H = 650px), visible = 260px, step to last line (idx 24)
    const totalLines = 25
    const curIdx = 24
    const ty = sourceTranslateY(curIdx, totalLines, VIS)
    // The highlighted line must be within [0, VIS) after applying translateY
    const lineTop = curIdx * ROW_H + ty
    expect(lineTop).toBeGreaterThanOrEqual(0)
    expect(lineTop).toBeLessThan(VIS)
  })

  it('keeps curIdx line top within [0, visiblePx) for every step of a 22-line source', () => {
    const totalLines = 22
    for (let curIdx = 0; curIdx < totalLines; curIdx++) {
      const ty = sourceTranslateY(curIdx, totalLines, VIS)
      const lineTop = curIdx * ROW_H + ty
      expect(lineTop, `curIdx=${curIdx} must be in view`).toBeGreaterThanOrEqual(0)
      expect(lineTop, `curIdx=${curIdx} must be in view`).toBeLessThan(VIS)
    }
  })
})

describe('markerLefts (hero geometry)', () => {
  it('emits a tick percent per change step at i/(total-1)*100', () => {
    const lefts = markerLefts(TRACE)
    expect(lefts[0]).toBeCloseTo(0)            // step 0 changed
    expect(lefts).not.toContain(3 / 8 * 100)   // step 3 (idx 3) has no change
    expect(lefts[lefts.length - 1]).toBeCloseTo(8 / 8 * 100) // step 8 changed
  })
  it('returns 50 (center) for a single-step trace instead of NaN (0/0)', () => {
    const single: Step[] = [
      { line: 1, event: 'call', changed: ['x'], scope: [v('x', 'scalar', { text: '1' })] },
    ]
    const lefts = markerLefts(single)
    expect(lefts).toHaveLength(1)
    expect(lefts[0]).toBe(50)
    expect(Number.isNaN(lefts[0])).toBe(false)
  })
})

describe('junctionOverlay', () => {
  it('dims not-taken arm bodies and chips the crossed arm', () => {
    const j: Junction[] = [{
      test_line: 3,
      arms: [
        { kind: 'if', lines: [4, 5], taken: true },
        { kind: 'else', lines: [7, 7], taken: false },
      ],
    }]
    const { role, chips } = junctionOverlay(j)
    expect(role[4]).toBeUndefined()   // taken arm: normal
    expect(role[5]).toBeUndefined()
    expect(role[7]).toBe('not-taken') // else body dimmed
    expect(chips[3]).toBe('→ if')
  })

  it('marks unknown arms distinctly under truncation', () => {
    const j: Junction[] = [{
      test_line: 3,
      arms: [
        { kind: 'if', lines: [4, 4], taken: null },
        { kind: 'else', lines: [6, 6], taken: null },
      ],
    }]
    const { role, chips } = junctionOverlay(j)
    expect(role[4]).toBe('unknown')
    expect(role[6]).toBe('unknown')
    expect(chips[3]).toBeUndefined()  // nothing crossed → no chip
  })

  it('suppresses the chip for a junction inside a dimmed (dead) range', () => {
    // outer took the else-arm (lines 8..9); the inner if at line 8 is dead code
    const j: Junction[] = [
      { test_line: 3, arms: [
        { kind: 'if', lines: [4, 5], taken: false },
        { kind: 'else', lines: [8, 9], taken: true },
      ] },
      { test_line: 4, arms: [   // nested inside the not-taken if-arm (4..5)
        { kind: 'if', lines: [5, 5], taken: false },
      ] },
    ]
    const { chips } = junctionOverlay(j)
    expect(chips[4]).toBeUndefined() // line 4 is inside the dimmed 4..5 range
  })

  it('returns empty maps for undefined junctions', () => {
    expect(junctionOverlay(undefined)).toEqual({ role: {}, chips: {} })
  })
})
