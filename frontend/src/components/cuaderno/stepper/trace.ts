import type { Step, Var } from '../../../types/api'

export const ROW_H = 26 // px — load-bearing: slab top = curIdx*ROW_H, line-height

const clamp = (n: number, lo: number, hi: number) => Math.min(Math.max(n, lo), hi)

// hero step is 1-based, clamped to [1, len]
export function clampStep(step: number, len: number): number {
  return clamp(step, 1, Math.max(len, 1))
}

// wraps modulo len, starts at k=1 so it never lands on the current step (handoff 837–839)
export function nextChange(cur: number, trace: Step[]): number {
  const len = trace.length
  for (let k = 1; k <= len; k++) {
    const i = (cur - 1 + k) % len
    if (trace[i].changed.length > 0) return i + 1
  }
  return cur
}

// click fraction (0..1) -> 1-based step (handoff 831–836)
export function trackFraction(f: number, len: number): number {
  return clamp(Math.round(f * (len - 1)) + 1, 1, len)
}

export type LineModel = { num: number; code: string; numStyle: string; codeStyle: string }

// curIdx < 0 (stale anchor, spec §7) marks NO line — the slab is suppressed by the caller.
export function lineModels(
  src: { num: number; text: string }[],
  curIdx: number,
): LineModel[] {
  return src.map((l, i) => {
    const on = i === curIdx // never true when curIdx < 0
    return {
      num: l.num,
      code: l.text,
      numStyle: `flex:none;width:30px;text-align:right;padding-right:14px;font-variant-numeric:tabular-nums;color:${on ? 'var(--accent-ink)' : 'var(--ink-4)'};font-weight:${on ? '700' : '400'};`,
      codeStyle: `white-space:pre;color:${on ? 'var(--ink)' : 'var(--ink-2)'};transition:color .3s ease;`,
    }
  })
}

export type RowModel = {
  name: string
  isScalar: boolean; isOpaque: boolean; isLarge: boolean; isObject: boolean
  text: string; label: string; summary: string; meta: string
  caret: string
  expandable: boolean
  rowStyle: string; dotStyle: string; nameStyle: string; valWrap: string
  scalarStyle: string; objStyle: string; chipStyle: string
  metaStyle: string; caretStyle: string; opaqueStyle: string
}

// 1:1 with the handoff mkRow (789–810). `expanded` is the name->bool map.
export function mkRow(
  name: string,
  def: Pick<Var, 'kind' | 'text' | 'label' | 'summary' | 'meta'>,
  changed: boolean,
  indent: number,
  expanded: Record<string, boolean>,
): RowModel {
  const exp = !!expanded[name]
  return {
    name,
    isScalar: def.kind === 'scalar', isOpaque: def.kind === 'opaque',
    isLarge: def.kind === 'large', isObject: def.kind === 'object',
    text: def.text || '', label: def.label || '', summary: def.summary || '', meta: def.meta || '',
    caret: exp ? '▾' : '▸',
    expandable: def.kind === 'large',
    rowStyle: `display:flex;align-items:baseline;gap:8px;padding:3.5px 0 3.5px ${indent ? 20 : 0}px;`,
    dotStyle: `flex:none;width:7px;text-align:center;color:var(--accent);opacity:${changed ? 1 : 0};font-size:8px;line-height:18px;`,
    nameStyle: `flex:none;color:${changed ? 'var(--ink-2)' : 'var(--ink-4)'};${indent ? 'opacity:.85;' : ''}`,
    valWrap: `flex:1;min-width:0;display:flex;justify-content:flex-end;align-items:baseline;`,
    scalarStyle: `color:${changed ? 'var(--accent-ink)' : 'var(--ink-3)'};font-weight:${changed ? '600' : '400'};white-space:nowrap;overflow:hidden;text-overflow:ellipsis;transition:color .3s ease;`,
    objStyle: `color:${changed ? 'var(--accent-ink)' : 'var(--ink-3)'};font-weight:${changed ? '600' : '400'};font-style:normal;transition:color .3s ease;`,
    chipStyle: `display:inline-flex;align-items:center;gap:6px;border:1px solid ${changed ? 'var(--accent-line)' : 'var(--hairline)'};background:var(--surface-2);border-radius:6px;padding:1px 8px;cursor:pointer;color:${changed ? 'var(--accent-ink)' : 'var(--ink-3)'};transition:color .3s ease,border-color .3s ease;`,
    metaStyle: `color:var(--ink-4);font-size:11px;`,
    caretStyle: `color:var(--ink-4);font-size:10px;`,
    opaqueStyle: `display:inline-flex;align-items:center;border:1px dashed var(--hairline);border-radius:6px;padding:1px 9px;color:var(--ink-4);`,
  }
}

// cumulative scope -> rows; large vars expand to non-changed scalar children at indent 1 (handoff 811–820)
export function buildRows(step: Step, expanded: Record<string, boolean>): RowModel[] {
  const out: RowModel[] = []
  step.scope.forEach((v) => {
    const changed = step.changed.includes(v.name)
    out.push(mkRow(v.name, v, changed, 0, expanded))
    if (v.kind === 'large' && expanded[v.name] && v.children) {
      v.children.forEach((c) => out.push(mkRow(c.name, { kind: 'scalar', text: c.text }, false, 1, expanded)))
    }
  })
  return out
}

/**
 * Compute the translateY (in px, always <= 0) that keeps the highlighted line
 * (at curIdx) fully visible inside a clipped source column of `visiblePx` height.
 *
 * Strategy: centre the line in the visible area, then clamp so we never scroll
 * past the top (translateY > 0) or past the bottom (content end stays at bottom).
 *
 * When curIdx < 0 (stale anchor) the slab is suppressed; return 0.
 */
export function sourceTranslateY(curIdx: number, totalLines: number, visiblePx: number): number {
  if (curIdx < 0 || totalLines === 0) return 0
  const contentH = totalLines * ROW_H
  // If all lines fit, no scroll needed
  if (contentH <= visiblePx) return 0
  // Ideal: centre the highlighted line in the visible area
  const ideal = -(curIdx * ROW_H - (visiblePx / 2 - ROW_H / 2))
  // Clamp: never scroll before the first line or past the last
  const maxScroll = -(contentH - visiblePx)
  return Math.min(0, Math.max(maxScroll, ideal))
}

// hero change-marker percents: i/(total-1)*100 for steps where changed.length>0 (handoff 862–864)
// guard: when total===1 the denominator is 0 (NaN); clamp to 50 (center of the track).
export function markerLefts(trace: Step[]): number[] {
  const total = trace.length
  const denom = total - 1
  return trace
    .map((t, i) => ({ on: t.changed.length > 0, left: denom === 0 ? 50 : (i / denom) * 100 }))
    .filter((m) => m.on)
    .map((m) => m.left)
}
