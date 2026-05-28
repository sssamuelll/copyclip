import { useEffect } from 'react'
import { usePlayground, type PlaygroundErrorInfo } from '../hooks/usePlayground'
import type { PlaygroundLaunchRequest } from '../types/api'

const BACKDROP_STYLE: React.CSSProperties = {
  position: 'fixed',
  inset: 0,
  background: 'rgba(0, 0, 0, 0.72)',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  zIndex: 10000,
  padding: 24,
}

const CARD_STYLE: React.CSSProperties = {
  background: 'var(--panel)',
  border: '1px solid var(--accent-cyan)',
  boxShadow: '0 0 0 1px var(--accent-cyan-soft), 0 30px 60px rgba(0, 0, 0, 0.5)',
  display: 'flex',
  flexDirection: 'column',
  width: '100%',
  maxWidth: 1200,
  // `height` is mandatory, not just `maxHeight`. The body iframe uses
  // `flex: 1` to fill remaining vertical space, but flex:1 collapses to
  // the iframe's intrinsic height (~150px default) when the parent has
  // no definite height. Setting height explicitly anchors the flex
  // calculation; the iframe now fills the card.
  height: '90vh',
  maxHeight: '90vh',
  overflow: 'hidden',
  color: 'var(--text-primary)',
}

const HEADER_STYLE: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: 16,
  padding: '12px 18px',
  borderBottom: '1px solid var(--border)',
  background: 'var(--accent-cyan-soft)',
  flex: '0 0 auto',
}

const BREADCRUMB_STYLE: React.CSSProperties = {
  fontFamily: "'JetBrains Mono', ui-monospace, monospace",
  fontSize: 12,
  letterSpacing: '0.3px',
  color: 'var(--accent-cyan)',
  textTransform: 'uppercase',
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
}

const CLOSE_BUTTON_STYLE: React.CSSProperties = {
  background: 'transparent',
  color: 'var(--accent-cyan)',
  border: '1px solid var(--accent-cyan)',
  width: 32,
  height: 32,
  cursor: 'pointer',
  fontSize: 18,
  lineHeight: 1,
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  fontFamily: 'inherit',
  flex: '0 0 auto',
}

const BODY_PADDING_STYLE: React.CSSProperties = {
  flex: 1,
  padding: 32,
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
  justifyContent: 'center',
  textAlign: 'center',
  gap: 16,
  overflow: 'auto',
}

const SPINNER_STYLE: React.CSSProperties = {
  width: 32,
  height: 32,
  border: '3px solid var(--border)',
  borderTopColor: 'var(--accent-cyan)',
  borderRadius: '50%',
  animation: 'playground-spin 0.8s linear infinite',
}

const PRIMARY_BUTTON_STYLE: React.CSSProperties = {
  background: 'var(--accent-cyan)',
  color: '#000',
  border: 'none',
  padding: '8px 18px',
  fontFamily: 'inherit',
  fontSize: 13,
  fontWeight: 500,
  cursor: 'pointer',
}

const SECONDARY_BUTTON_STYLE: React.CSSProperties = {
  background: 'transparent',
  color: 'var(--accent-cyan)',
  border: '1px solid var(--accent-cyan)',
  padding: '8px 18px',
  fontFamily: 'inherit',
  fontSize: 13,
  cursor: 'pointer',
}

const CODE_BLOCK_STYLE: React.CSSProperties = {
  background: 'var(--bg)',
  border: '1px solid var(--border)',
  padding: '10px 14px',
  fontFamily: "'JetBrains Mono', ui-monospace, monospace",
  fontSize: 13,
  color: 'var(--text-primary)',
  userSelect: 'all',
}

const PRE_STYLE: React.CSSProperties = {
  background: 'var(--bg)',
  border: '1px solid var(--border)',
  padding: 12,
  fontFamily: "'JetBrains Mono', ui-monospace, monospace",
  fontSize: 12,
  color: 'var(--text-secondary)',
  maxHeight: 200,
  maxWidth: '100%',
  overflow: 'auto',
  textAlign: 'left',
  whiteSpace: 'pre-wrap',
  wordBreak: 'break-word',
  userSelect: 'text',
}

const SUBTITLE_STYLE: React.CSSProperties = {
  fontSize: 14,
  color: 'var(--text-secondary)',
  margin: 0,
  maxWidth: 560,
  lineHeight: 1.5,
}

const TITLE_STYLE: React.CSSProperties = {
  margin: 0,
  fontFamily: "'JetBrains Mono', ui-monospace, monospace",
  fontSize: 18,
  letterSpacing: '0.3px',
  color: 'var(--text-primary)',
}

// Inject the spinner keyframes once. Other pages use inline styles too and
// there's no shared place for keyframes, so we colocate with the component.
const SPINNER_KEYFRAMES = `@keyframes playground-spin { to { transform: rotate(360deg); } }`

export function PlaygroundPanel() {
  const { state, launch, close } = usePlayground()

  // ESC closes the panel from any state except idle. Attached once and only
  // active while the panel is visible.
  useEffect(() => {
    if (state.kind === 'idle') return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        void close()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [state.kind, close])

  if (state.kind === 'idle') return null

  const onBackdropClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget) {
      void close()
    }
  }

  return (
    <>
      <style>{SPINNER_KEYFRAMES}</style>
      <div
        style={BACKDROP_STYLE}
        onClick={onBackdropClick}
        role="dialog"
        aria-modal="true"
        aria-label="Anchored playground"
      >
        <div style={CARD_STYLE}>
          <PanelHeader req={state.req} onClose={() => void close()} />
          {state.kind === 'loading' && <LoadingBody req={state.req} />}
          {state.kind === 'ready' && <ReadyBody iframeUrl={state.res.iframe_url} />}
          {state.kind === 'error' && (
            <ErrorBody
              error={state.error}
              onRetry={() => void launch(state.req)}
              onClose={() => void close()}
            />
          )}
        </div>
      </div>
    </>
  )
}

function PanelHeader({
  req,
  onClose,
}: {
  req: PlaygroundLaunchRequest
  onClose: () => void
}) {
  return (
    <div style={HEADER_STYLE}>
      <span style={BREADCRUMB_STYLE} title={req.breadcrumb}>
        {req.breadcrumb || 'Playground'}
      </span>
      <button
        type="button"
        onClick={onClose}
        style={CLOSE_BUTTON_STYLE}
        aria-label="Close playground"
        title="Close (ESC)"
      >
        ×
      </button>
    </div>
  )
}

function LoadingBody({ req }: { req: PlaygroundLaunchRequest }) {
  return (
    <div style={BODY_PADDING_STYLE}>
      <div style={SPINNER_STYLE} aria-hidden="true" />
      <h2 style={TITLE_STYLE}>Preparing playground</h2>
      <p style={SUBTITLE_STYLE}>
        Spawning a Marimo notebook for <code style={{ color: 'var(--accent-cyan)' }}>{req.function_ref.name}</code>.
        This usually takes a few seconds the first time.
      </p>
    </div>
  )
}

function ReadyBody({ iframeUrl }: { iframeUrl: string }) {
  return (
    <iframe
      src={iframeUrl}
      title="Anchored playground"
      // allow-same-origin is required for marimo's websockets to its own
      // 127.0.0.1:{port} origin. The iframe origin differs from the
      // dashboard origin so this does not grant access to dashboard state.
      sandbox="allow-scripts allow-same-origin allow-forms"
      style={{ flex: 1, width: '100%', border: 0, background: 'var(--bg)' }}
    />
  )
}

function ErrorBody({
  error,
  onRetry,
  onClose,
}: {
  error: PlaygroundErrorInfo
  onRetry: () => void
  onClose: () => void
}) {
  if (error.code === 'marimo_not_installed') {
    const hint = error.install_hint || 'pip install copyclip[playground]'
    return (
      <div style={BODY_PADDING_STYLE}>
        <h2 style={TITLE_STYLE}>Marimo isn't installed</h2>
        <p style={SUBTITLE_STYLE}>
          The Anchored Playground spawns Marimo notebooks under the hood, but the marimo package
          isn't available in this CopyClip install. Run the command below in your terminal, then retry.
        </p>
        <code style={CODE_BLOCK_STYLE}>{hint}</code>
        <div style={{ display: 'flex', gap: 12 }}>
          <button type="button" style={PRIMARY_BUTTON_STYLE} onClick={onRetry}>
            Done, retry
          </button>
          <button type="button" style={SECONDARY_BUTTON_STYLE} onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    )
  }

  if (error.code === 'function_not_found') {
    return (
      <div style={BODY_PADDING_STYLE}>
        <h2 style={TITLE_STYLE}>Function not found in the index</h2>
        <p style={SUBTITLE_STYLE}>
          This function was renamed, moved, or deleted since the last analysis. Re-run analyze to refresh the
          codebase map, then open the playground from the updated symbol.
        </p>
        <button type="button" style={SECONDARY_BUTTON_STYLE} onClick={onClose}>
          Close
        </button>
      </div>
    )
  }

  if (error.code === 'marimo_spawn_failed') {
    return (
      <div style={BODY_PADDING_STYLE}>
        <h2 style={TITLE_STYLE}>Marimo failed to start</h2>
        <p style={SUBTITLE_STYLE}>
          CopyClip launched the subprocess but it exited or didn't respond in time. The first lines of its stderr
          are below — copy them if you file a report.
        </p>
        <pre style={PRE_STYLE}>{error.message}</pre>
        <div style={{ display: 'flex', gap: 12 }}>
          <button type="button" style={PRIMARY_BUTTON_STYLE} onClick={onRetry}>
            Retry
          </button>
          <button type="button" style={SECONDARY_BUTTON_STYLE} onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    )
  }

  if (error.code === 'no_free_port') {
    return (
      <div style={BODY_PADDING_STYLE}>
        <h2 style={TITLE_STYLE}>Too many playgrounds open</h2>
        <p style={SUBTITLE_STYLE}>
          CopyClip caps concurrent playgrounds to keep your machine responsive. Close one of the open notebooks,
          then try again.
        </p>
        <button type="button" style={SECONDARY_BUTTON_STYLE} onClick={onClose}>
          Close
        </button>
      </div>
    )
  }

  if (error.code === 'invalid_request' || error.code === 'invalid_function_ref') {
    return (
      <div style={BODY_PADDING_STYLE}>
        <h2 style={TITLE_STYLE}>This symbol can't be opened in a playground</h2>
        <p style={SUBTITLE_STYLE}>
          The request didn't match the playground's launch contract. This usually means the symbol isn't a
          plain function or method — open one of the suggested callable symbols instead.
        </p>
        <button type="button" style={SECONDARY_BUTTON_STYLE} onClick={onClose}>
          Close
        </button>
      </div>
    )
  }

  return (
    <div style={BODY_PADDING_STYLE}>
      <h2 style={TITLE_STYLE}>Something went wrong launching the playground</h2>
      <p style={SUBTITLE_STYLE}>{error.message || 'Unknown error.'}</p>
      <div style={{ display: 'flex', gap: 12 }}>
        <button type="button" style={PRIMARY_BUTTON_STYLE} onClick={onRetry}>
          Retry
        </button>
        <button type="button" style={SECONDARY_BUTTON_STYLE} onClick={onClose}>
          Close
        </button>
      </div>
    </div>
  )
}
