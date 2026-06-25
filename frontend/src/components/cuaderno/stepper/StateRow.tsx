import type { CSSProperties } from 'react'
import type { RowModel } from './trace'

// parse a "a:b;c:d;" inline-style string into a React style object
export function s(css: string): CSSProperties {
  const out: Record<string, string> = {}
  css.split(';').forEach((decl) => {
    const i = decl.indexOf(':')
    if (i < 0) return
    const prop = decl.slice(0, i).trim()
    const val = decl.slice(i + 1).trim()
    if (!prop) return
    const camel = prop.replace(/-([a-z])/g, (_, c: string) => c.toUpperCase())
    out[camel] = val
  })
  return out as CSSProperties
}

type Props = {
  row: RowModel
  onToggle: (name: string) => void
}

export function StateRow({ row, onToggle }: Props) {
  return (
    <div style={s(row.rowStyle)}>
      <span style={s(row.dotStyle)}>◆</span>
      <span style={s(row.nameStyle)}>{row.name}</span>
      <span style={s(row.valWrap)}>
        {row.isScalar && <span style={s(row.scalarStyle)}>{row.text}</span>}
        {row.isObject && <span style={s(row.objStyle)}>{row.text}</span>}
        {row.isOpaque && <span style={s(row.opaqueStyle)}>‹{row.label}›</span>}
        {row.isLarge && (
          <span
            style={s(row.chipStyle)}
            onClick={row.expandable ? () => onToggle(row.name) : undefined}
          >
            {row.summary} <span style={s(row.metaStyle)}>{row.meta}</span>
            <span style={s(row.caretStyle)}> {row.caret}</span>
          </span>
        )}
      </span>
    </div>
  )
}
