import { describe, it, expect } from 'vitest'
import type { Step, Var } from '../../../types/api'
import { clampStep, nextChange, trackFraction, lineModels, buildRows, markerLefts } from './trace'

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
