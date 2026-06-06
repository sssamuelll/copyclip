import type { ReactNode } from 'react'

// Inline markup the model emits inside text fields. Backticks are the canonical
// form (per the system prompt); the HTML-ish tags are tolerated because the
// model sometimes invents them (<mono>…</mono>) and sealed history already
// contains them. Anything unmatched — including unclosed tags — renders as
// plain text; this parser never swallows content.
const INLINE_RE =
  /<(mono|code|tt)>([\s\S]*?)<\/\1>|<(b|strong)>([\s\S]*?)<\/\3>|<(i|em)>([\s\S]*?)<\/\5>|`([^`\n]+)`|\*\*([^*\n]+?)\*\*/g

export function renderInline(text: string): ReactNode {
  if (!/[<`*]/.test(text)) return text
  const out: ReactNode[] = []
  let last = 0
  let m: RegExpExecArray | null
  INLINE_RE.lastIndex = 0
  while ((m = INLINE_RE.exec(text)) !== null) {
    if (m.index > last) out.push(text.slice(last, m.index))
    const key = `${m.index}`
    const code = m[2] ?? m[7]
    const bold = m[4] ?? m[8]
    const italic = m[6]
    if (code !== undefined) {
      out.push(
        <code key={key} className="ic">
          {code}
        </code>,
      )
    } else if (bold !== undefined) {
      out.push(<strong key={key}>{bold}</strong>)
    } else if (italic !== undefined) {
      out.push(<em key={key}>{italic}</em>)
    }
    last = m.index + m[0].length
  }
  if (out.length === 0) return text
  if (last < text.length) out.push(text.slice(last))
  return out
}
