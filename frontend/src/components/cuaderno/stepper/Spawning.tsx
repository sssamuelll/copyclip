import type { Citation } from '../../../types/api'
import { CitationChip } from '../CitationChip'
import { t } from '../strings'
import { s } from './StateRow'

type Props = {
  funcName: string
  callText: string
  citation?: Citation
  breadcrumb?: string
  onOpenCitation?: (c: Citation) => void
  lang?: string | null
}

export function Spawning({ funcName, callText, citation, breadcrumb, onOpenCitation, lang }: Props) {
  return (
    <div className="widget stepper-widget">
      <div style={s('display:flex;align-items:center;gap:9px;padding:9px 14px;border-bottom:1px solid var(--hairline-soft);')}>
        <span style={s('font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:var(--ink-3);font-weight:600;')}>Playground</span>
        <span style={s('color:var(--ink-4);')}>·</span>
        <span style={s('font-family:var(--font-mono);font-size:12px;color:var(--accent-ink);')}>{funcName}</span>
      </div>
      <div style={{ ...s('display:flex;flex-direction:column;align-items:center;justify-content:center;padding:24px;'), height: 430 }}>
        <div style={s('font-family:var(--font-mono);font-size:13px;color:var(--ink-3);margin-bottom:20px;')}>{callText}</div>
        <div style={s('position:relative;width:220px;height:4px;border-radius:2px;background:var(--surface-2);overflow:hidden;margin-bottom:20px;')}>
          <div className="stepper-sweep" style={s('position:absolute;top:0;left:0;height:100%;width:34%;border-radius:2px;background:var(--accent-line);')} />
        </div>
        <div style={s('font-size:14px;color:var(--ink-2);font-family:var(--font-ui);display:flex;align-items:center;gap:7px;')}>
          {t('playground_preparing', lang)} <span className="stepper-pulse" style={s('color:var(--ink-3);')}>{t('playground_preparing_capturing', lang)}</span>
        </div>
        {breadcrumb || citation ? (
          <div className="playground-breadcrumb-row" style={s('display:flex;align-items:center;gap:8px;margin-top:16px;flex-wrap:wrap;justify-content:center;')}>
            {breadcrumb ? <span className="playground-breadcrumb" style={s('font-size:11.5px;color:var(--ink-3);')}>{breadcrumb}</span> : null}
            {citation && onOpenCitation ? <CitationChip citation={citation} onClick={onOpenCitation} /> : null}
          </div>
        ) : null}
      </div>
    </div>
  )
}
