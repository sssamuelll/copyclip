import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { GraphView } from './GraphView'
import type { GraphViewWidget } from '../../../types/api'

const widget: GraphViewWidget = {
  kind: 'graph_view',
  nodes: [
    { id: 'pkg/a', label: 'a', citation: { kind: 'path', path: 'pkg/a.py' }, heat: 90 },
    { id: 'pkg/b', label: 'b', citation: { kind: 'path', path: 'pkg/b.py' }, heat: null },
  ],
  edges: [{ from: 'pkg/a', to: 'pkg/b' }],
}

// The node <rect> carries a <title> with the node label; its parent is the rect.
function nodeRect(container: HTMLElement, label: string): Element {
  const title = Array.from(container.querySelectorAll('title')).find(
    (t) => t.textContent === label,
  )
  if (!title || !title.parentElement) throw new Error(`no node rect for ${label}`)
  return title.parentElement
}

describe('GraphView fog', () => {
  it('paints a measured node with a cyan band fill', () => {
    const { container } = render(<GraphView widget={widget} onOpenCitation={() => {}} />)
    const fill = nodeRect(container, 'a').getAttribute('fill') || ''
    expect(fill).toContain('--accent-cyan')
  })

  it('renders an explicitly-unmeasured node (null) as a dashed third state, not cyan', () => {
    const { container } = render(<GraphView widget={widget} onOpenCitation={() => {}} />)
    const rect = nodeRect(container, 'b')
    expect(rect.getAttribute('fill') || '').not.toContain('--accent-cyan')
    expect(rect.getAttribute('stroke-dasharray')).toBeTruthy() // dashed = unmeasured
  })

  it('spreads a compressed band across the ramp (relative, not absolute)', () => {
    // All four are "high" in absolute terms (50-60) — absolute bands would paint
    // them identically. Relative bands must make the hottest stand out.
    const w: GraphViewWidget = {
      kind: 'graph_view',
      nodes: [
        { id: 'a', label: 'a', citation: { kind: 'path', path: 'a.py' }, heat: 50 },
        { id: 'b', label: 'b', citation: { kind: 'path', path: 'b.py' }, heat: 53 },
        { id: 'c', label: 'c', citation: { kind: 'path', path: 'c.py' }, heat: 57 },
        { id: 'd', label: 'd', citation: { kind: 'path', path: 'd.py' }, heat: 60 },
      ],
      edges: [{ from: 'a', to: 'b' }, { from: 'b', to: 'c' }, { from: 'c', to: 'd' }],
    }
    const { container } = render(<GraphView widget={w} onOpenCitation={() => {}} />)
    const hot = nodeRect(container, 'd').getAttribute('fill') || ''
    const cool = nodeRect(container, 'a').getAttribute('fill') || ''
    expect(hot).not.toBe(cool)        // absolute bands would make these equal
    expect(hot).toContain('60%')      // hottest -> critical end of the ramp
    expect(cool).toContain('--accent-cyan') // coolest still cyan, just faint
  })

  it('renders a non-fog node (score absent) normally — no dash, no cyan', () => {
    // A node with no heat key (e.g. a caller/callee symbol) has
    // no debt concept; it must look like a plain node, never dashed.
    const w: GraphViewWidget = {
      kind: 'graph_view',
      nodes: [{ id: 'main', label: 'main', citation: { kind: 'path', path: 'm.py' } }],
      edges: [],
    }
    const { container } = render(<GraphView widget={w} onOpenCitation={() => {}} />)
    const rect = nodeRect(container, 'main')
    expect(rect.getAttribute('fill') || '').not.toContain('--accent-cyan')
    expect(rect.getAttribute('stroke-dasharray')).toBeFalsy() // not dashed
  })
})
