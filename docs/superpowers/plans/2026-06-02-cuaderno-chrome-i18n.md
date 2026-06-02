# Cuaderno UI-Chrome i18n Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the cuaderno's fixed UI chrome (you asked / does this answer the question / I got this / I didn't / go deeper / status banners) mirror the question's detected language (es/en), live and on restore, instead of being hardcoded English.

**Architecture:** Carry the authoritative `detect_language(question)` value to the renderer via two carriers — the SSE `meta` event (live, no flicker) and a persisted `Frame.question_language` (restore). The frontend reads it and looks chrome strings up in a two-locale dictionary; `unknown`/absent → English. Backend localizes the two strings the *code* injects (the fallback-frame text and the partial marker). Scope is the answer-turn chrome only; the periphery (empty state, Settings, breadcrumbs) stays English.

**Tech Stack:** Python 3 (pytest, run from repo root `C:\Users\simon\Desktop\projects\copyclip` with `python -m pytest <path>::<test> -v`); React + TypeScript + Vite frontend. **No frontend test runner exists** (only `tsc -b`); frontend tasks are verified by `npm --prefix frontend run build` (which runs `tsc -b`) plus the pure `strings.ts` module being self-evidently correct. Adding vitest is a deliberate non-goal (YAGNI: zero existing frontend tests).

**Spec:** `docs/superpowers/specs/2026-06-02-cuaderno-chrome-i18n-design.md`

---

## Orientation (read once)

Verified facts:

- **Language detector** `src/copyclip/intelligence/cuaderno/language.py:detect_language(text) -> "es" | "en" | "unknown"`.
- **Frame** (`schema.py:140-163`): `question`, `blocks`, `status=FRAME_STATUS_ANSWER`, `verdict: Optional[dict]=None`; `frame_to_dict` writes those four keys; `frame_from_dict` reads them (status default legacy, verdict default None).
- **Compositor seal points** (`compositor.py`): `_seal(question, emitted, status, verdict)` (used by the in-loop terminals + `_sealed_frame`) and `_fallback_frame(question, reason)` (budget/no-blocks). Every terminal frame flows through one of these.
- **ask_stream** (`ask_stream.py`): `iter_ask_events` yields `{"type":"meta","session_id":...}` first (line 41); `_persist_partial(conn, session_id, question, emitted, message=None)` builds the partial frame (currently sets no `question_language`).
- **Frontend wiring:** `pages/CuadernoPage.tsx` handles the `meta` event (lines 86-96, reads `e.session_id`), holds state, passes props to `<Cuaderno>`. `components/cuaderno/Cuaderno.tsx` renders `<FrameMidStream>` (live, scene 'midstream'/'writing') and `<FrameDynamic frame={activeQuestion.frame}>` (terminal, scene 'frame') and `<GotItMarkers>`. SSE parsing in `api/cuaderno.ts:askStream` passes any JSON through (no change needed). Types in `types/api.ts`: `Frame` (lines 835-840), `CuadernoStreamEvent` union (lines 863-876, meta variant line 864).
- **Chrome strings to translate** (answer-turn only): `GotItMarkers.tsx:10-34`; `FrameDynamic.tsx` STATUS_BANNER `6-23`, "you asked" `:60`, "go deeper" `:199`; `FrameMidStream.tsx` "you asked" `:13`, "running…" `:36`. Block kickers and follow-up items are **model-generated** (already localized) — not chrome.

**Files created/modified:**
```
src/copyclip/intelligence/cuaderno/schema.py        (modify: Frame.question_language)        T1
src/copyclip/intelligence/cuaderno/i18n.py          (create: backend injected strings + tr)  T2
src/copyclip/intelligence/cuaderno/compositor.py    (modify: seals set lang + localized fallback) T2
src/copyclip/intelligence/cuaderno/ask_stream.py    (modify: meta event + localized partial)  T3
tests/test_cuaderno_chrome_i18n.py                  (create: backend tests)                   T1-T3
frontend/src/types/api.ts                           (modify: Frame + meta types)              T4
frontend/src/components/cuaderno/strings.ts         (create: es/en dict + t())                T5
frontend/src/components/cuaderno/GotItMarkers.tsx   (modify)                                  T6
frontend/src/components/cuaderno/frames/FrameDynamic.tsx   (modify)                           T6
frontend/src/components/cuaderno/frames/FrameMidStream.tsx (modify)                           T6
frontend/src/components/cuaderno/Cuaderno.tsx       (modify: thread questionLanguage)         T6
frontend/src/pages/CuadernoPage.tsx                 (modify: capture meta lang)               T6
```

---

## Task 1: `Frame.question_language` (schema + persistence)

**Files:**
- Modify: `src/copyclip/intelligence/cuaderno/schema.py:140-163`
- Test: `tests/test_cuaderno_chrome_i18n.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_cuaderno_chrome_i18n.py`:

```python
from copyclip.intelligence.cuaderno.schema import (
    Frame, Block, frame_to_dict, frame_from_dict,
)


def test_frame_carries_question_language_round_trip():
    f = Frame(question="¿cómo?", blocks=[Block.paragraph("x")],
              status="answer", verdict=None, question_language="es")
    d = frame_to_dict(f)
    assert d["question_language"] == "es"
    back = frame_from_dict(d)
    assert back.question_language == "es"


def test_legacy_frame_defaults_question_language_none():
    # A stored frame from before this field existed.
    d = {"question": "q", "blocks": [], "status": "legacy"}
    assert frame_from_dict(d).question_language is None
```

- [ ] **Step 2: Run, verify fail**

Run: `python -m pytest tests/test_cuaderno_chrome_i18n.py -v`
Expected: FAIL — `Frame.__init__() got an unexpected keyword argument 'question_language'`.

- [ ] **Step 3: Implement**

In `src/copyclip/intelligence/cuaderno/schema.py`, add the field to `Frame` (after `verdict`):

```python
@dataclass
class Frame:
    question: str
    blocks: list[Block]
    status: str = FRAME_STATUS_ANSWER
    verdict: Optional[dict[str, Any]] = None
    question_language: Optional[str] = None
```

Update `frame_to_dict` to write it:

```python
def frame_to_dict(f: Frame) -> dict[str, Any]:
    return {
        "question": f.question,
        "blocks": [b.to_dict() for b in f.blocks],
        "status": f.status,
        "verdict": f.verdict,
        "question_language": f.question_language,
    }
```

Update `frame_from_dict` to read it (default `None`):

```python
def frame_from_dict(d: dict[str, Any]) -> Frame:
    return Frame(
        question=d["question"],
        blocks=[Block.from_dict(b) for b in d["blocks"]],
        status=d.get("status", FRAME_STATUS_LEGACY),
        verdict=d.get("verdict"),
        question_language=d.get("question_language"),
    )
```

- [ ] **Step 4: Run, verify pass**

Run: `python -m pytest tests/test_cuaderno_chrome_i18n.py -v`
Expected: both PASS.

- [ ] **Step 5: Commit**

```bash
git add src/copyclip/intelligence/cuaderno/schema.py tests/test_cuaderno_chrome_i18n.py
git commit -m "feat(cuaderno): Frame.question_language (persisted, default None for legacy)"
```

---

## Task 2: backend `i18n.py` + compositor seals set language + localized fallback

**Files:**
- Create: `src/copyclip/intelligence/cuaderno/i18n.py`
- Modify: `src/copyclip/intelligence/cuaderno/compositor.py`
- Test: `tests/test_cuaderno_chrome_i18n.py` (append)

- [ ] **Step 1: Append the failing tests**

Add to `tests/test_cuaderno_chrome_i18n.py`:

```python
from copyclip.intelligence.cuaderno.i18n import tr
from copyclip.intelligence.cuaderno import compositor


def test_tr_picks_locale_and_falls_back_to_en():
    assert tr("fallback", "es", reason="x") != tr("fallback", "en", reason="x")
    # unknown / None -> English
    assert tr("fallback", "unknown", reason="x") == tr("fallback", "en", reason="x")
    assert tr("fallback", None, reason="x") == tr("fallback", "en", reason="x")


def test_fallback_frame_sets_language_and_localizes_text():
    es = compositor._fallback_frame("¿cómo funciona el compositor?", "budget")
    en = compositor._fallback_frame("how does the compositor work?", "budget")
    assert es.question_language == "es"
    assert en.question_language == "en"
    es_text = es.blocks[0].data["text"]
    en_text = en.blocks[0].data["text"]
    assert es_text != en_text  # localized
    assert es.status == "fallback" and en.status == "fallback"


def test_seal_sets_question_language():
    fd = compositor._seal("¿qué es esto?", [Block.paragraph("respuesta")],
                          "answer", {"source": "cheap"})
    assert fd["question_language"] == "es"
```

- [ ] **Step 2: Run, verify fail**

Run: `python -m pytest tests/test_cuaderno_chrome_i18n.py -v`
Expected: FAIL — `No module named 'copyclip.intelligence.cuaderno.i18n'` and `_fallback_frame`/`_seal` not setting language.

- [ ] **Step 3: Implement**

(a) Create `src/copyclip/intelligence/cuaderno/i18n.py`:

```python
"""Localized strings the CODE injects into a user-facing frame (NOT the model).
Mirrors the question's detected language; unknown/absent -> English. Two locales
only (the detector serves es/en); no i18n library."""
from __future__ import annotations

from typing import Optional

_STRINGS = {
    "en": {
        "fallback": ("I couldn't finish this turn — {reason}. Try rephrasing, or "
                     "ask a narrower question (a specific file, function, or commit)."),
        "partial": "This turn was interrupted ({reason}). Re-ask to retry.",
        "partial_default_reason": "the stream ended early",
    },
    "es": {
        "fallback": ("No pude terminar este turno — {reason}. Reformula, o haz una "
                     "pregunta más acotada (un archivo, función o commit específico)."),
        "partial": "Este turno se interrumpió ({reason}). Vuelve a preguntar para reintentar.",
        "partial_default_reason": "el stream se cortó temprano",
    },
}


def tr(key: str, lang: Optional[str], **kwargs) -> str:
    table = _STRINGS["es"] if lang == "es" else _STRINGS["en"]
    template = table.get(key) or _STRINGS["en"][key]
    return template.format(**kwargs) if kwargs else template
```

(b) In `src/copyclip/intelligence/cuaderno/compositor.py`, add imports near the top (with the other `from .` imports):

```python
from .language import detect_language
from .i18n import tr
```

Replace `_fallback_frame` (currently lines 44-54):

```python
def _fallback_frame(question: str, reason: str) -> Frame:
    lang = detect_language(question)
    return Frame(
        question=question,
        blocks=[Block.paragraph(tr("fallback", lang, reason=reason))],
        status=FRAME_STATUS_FALLBACK,
        question_language=lang,
    )
```

Replace `_seal` (currently lines 71-72):

```python
def _seal(question: str, emitted: list[Block], status: str, verdict: dict) -> dict[str, Any]:
    return frame_to_dict(Frame(question=question, blocks=emitted, status=status,
                               verdict=verdict, question_language=detect_language(question)))
```

(Both `_seal` and `_fallback_frame` are the only Frame constructors in the compositor; every terminal path uses one of them, so all statuses now carry `question_language`.)

- [ ] **Step 4: Run, verify pass**

Run: `python -m pytest tests/test_cuaderno_chrome_i18n.py -v`
Expected: all PASS.
Then confirm no compositor regression:
Run: `python -m pytest tests/test_cuaderno_compositor.py tests/test_cuaderno_retry_recovery.py -q`
Expected: all PASS. (The fallback text changed wording — if any existing test asserts the exact old English fallback string, update that assertion to match the new `tr("fallback","en",...)` text; the meaning is unchanged.)

- [ ] **Step 5: Commit**

```bash
git add src/copyclip/intelligence/cuaderno/i18n.py src/copyclip/intelligence/cuaderno/compositor.py tests/test_cuaderno_chrome_i18n.py
git commit -m "feat(cuaderno): seals carry question_language; fallback text localized (es/en)"
```

---

## Task 3: ask_stream — `meta` carries language + localized partial marker

**Files:**
- Modify: `src/copyclip/intelligence/cuaderno/ask_stream.py`
- Test: `tests/test_cuaderno_chrome_i18n.py` (append)

- [ ] **Step 1: Append the failing tests**

Add to `tests/test_cuaderno_chrome_i18n.py`:

```python
from copyclip.intelligence.cuaderno import ask_stream
from tests.test_cuaderno_compositor import StubStream, _tool_stop, _content, _msg_stop


def test_meta_event_carries_question_language(tmp_path):
    # The meta event is yielded FIRST, before iter_compose_events runs or any
    # save_question touches the DB — so pull just that event and close the
    # generator (avoids save_question(conn=None) on the trailing frame event).
    client = StubStream([_msg_stop("end_turn", [])])
    gen = ask_stream.iter_ask_events(
        client=client, question="¿cómo funciona esto?", project_root=str(tmp_path),
        project_id=1, conn=None, session_id="s1", max_tool_rounds=1)
    meta = next(gen)
    gen.close()
    assert meta["type"] == "meta"
    assert meta["question_language"] == "es"


def test_persist_partial_sets_language_and_localizes(tmp_path, monkeypatch):
    saved = []
    monkeypatch.setattr(ask_stream, "save_question",
                        lambda conn, sid, q, frame: saved.append(frame))
    ask_stream._persist_partial(None, "s1", "¿cómo?", [], message="boom")
    assert saved[0].question_language == "es"
    es_text = saved[0].blocks[0].data["text"]
    saved.clear()
    ask_stream._persist_partial(None, "s1", "how does it work?", [], message="boom")
    assert saved[0].question_language == "en"
    assert saved[0].blocks[0].data["text"] != es_text  # localized
```

- [ ] **Step 2: Run, verify fail**

Run: `python -m pytest tests/test_cuaderno_chrome_i18n.py -v`
Expected: FAIL — meta event has no `question_language`; `_persist_partial` sets no language / English-only marker.

- [ ] **Step 3: Implement**

In `src/copyclip/intelligence/cuaderno/ask_stream.py`, add imports (with the existing `from .` imports):

```python
from .language import detect_language
from .i18n import tr
```

Replace `_persist_partial` (currently lines 11-19, the post-retry-fix version) with:

```python
def _persist_partial(conn, session_id: str, question: str, emitted: list[dict],
                     message: Optional[str] = None) -> None:
    lang = detect_language(question)
    blocks = [Block.from_dict(b) for b in emitted]
    if not blocks:
        reason = message or tr("partial_default_reason", lang)
        blocks = [Block.paragraph(tr("partial", lang, reason=reason))]
    pframe = Frame(question=question, blocks=blocks, status=FRAME_STATUS_PARTIAL,
                   question_language=lang)
    save_question(conn, session_id, question, pframe)
```

Update the `meta` event (currently line 41) to carry the language:

```python
    yield {"type": "meta", "session_id": session_id,
           "question_language": detect_language(question)}
```

- [ ] **Step 4: Run, verify pass**

Run: `python -m pytest tests/test_cuaderno_chrome_i18n.py -v`
Expected: all PASS.
Then: `python -m pytest tests/test_cuaderno_ask_stream.py tests/test_cuaderno_sse_response.py tests/test_cuaderno_retry_recovery.py -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/copyclip/intelligence/cuaderno/ask_stream.py tests/test_cuaderno_chrome_i18n.py
git commit -m "feat(cuaderno): meta event carries question_language; partial marker localized"
```

---

## Task 4: frontend types

**Files:**
- Modify: `frontend/src/types/api.ts:835-876`

- [ ] **Step 1: Add the fields**

In `frontend/src/types/api.ts`, extend the `Frame` type (add after `verdict?`):

```typescript
export type Frame = {
  question: string
  blocks: Block[]
  status?: FrameStatus
  verdict?: Record<string, unknown> | null
  question_language?: string | null
}
```

Extend the `meta` variant of `CuadernoStreamEvent`:

```typescript
  | { type: 'meta'; session_id: string; question_language?: string | null }
```

- [ ] **Step 2: Typecheck**

Run: `npm --prefix frontend run build`
Expected: `tsc -b` passes (no type errors). (A full `vite build` also runs — that's fine.)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types/api.ts
git commit -m "feat(cuaderno-fe): Frame.question_language + meta.question_language types"
```

---

## Task 5: frontend strings module

**Files:**
- Create: `frontend/src/components/cuaderno/strings.ts`

> **Microcopy note:** the Spanish strings below are a first pass (Venezuelan tuteo, no AI-slop). Before shipping, run a `solace-wren` microcopy review over the `es` block to tighten voice. Do NOT change the `en` strings (they match the current UI verbatim).

- [ ] **Step 1: Create the module**

Create `frontend/src/components/cuaderno/strings.ts`:

```typescript
// Two-locale chrome strings for the answer-turn UI. unknown/absent -> en.
// The `en` values are verbatim the strings the components shipped with.
type Lang = 'es' | 'en'

const STRINGS: Record<Lang, Record<string, string>> = {
  en: {
    gotit_prompt: 'does this answer the question?',
    gotit_got: 'I got this',
    gotit_didnt: "I didn't",
    gotit_marked_got: '✓ marked: got this',
    gotit_saved_pre: 'saved to ',
    gotit_saved_mid: 'this matters',
    gotit_saved_post: '. ask anything else when ready.',
    gotit_marked_didnt: "↻ marked: didn't",
    gotit_didnt_msg: 'where did it break? try a follow-up below or rephrase.',
    you_asked: 'you asked',
    go_deeper: 'go deeper',
    running: 'running…',
    banner_ungrounded_kicker: 'not grounded',
    banner_ungrounded_text:
      'This answer is not anchored to code the tutor actually read, so it may be invented. Either the project does not cover this, or the tutor answered too soon. Re-ask, or point at a specific file, function, or commit.',
    banner_off_target_kicker: 'off target',
    banner_off_target_text:
      'This is grounded in the code, but it answers a different question than you asked. Re-ask to redirect it to what you meant.',
    banner_insufficient_evidence_kicker: 'insufficient evidence',
    banner_insufficient_evidence_text:
      'The tutor looked but the project does not contain enough to answer this confidently. What it would need is named above.',
    banner_partial_kicker: 'partial answer',
    banner_partial_text: 'This answer was interrupted before it finished. It may be incomplete.',
    banner_fallback_kicker: 'no answer',
    banner_fallback_text: 'The tutor could not produce an answer for this question this time.',
  },
  es: {
    gotit_prompt: '¿esto responde la pregunta?',
    gotit_got: 'lo capté',
    gotit_didnt: 'no lo capté',
    gotit_marked_got: '✓ marcado: lo capté',
    gotit_saved_pre: 'guardado en ',
    gotit_saved_mid: 'esto importa',
    gotit_saved_post: '. pregunta lo que quieras cuando estés listo.',
    gotit_marked_didnt: '↻ marcado: no lo capté',
    gotit_didnt_msg: '¿dónde se rompió? prueba un seguimiento abajo o reformula.',
    you_asked: 'preguntaste',
    go_deeper: 'profundiza',
    running: 'corriendo…',
    banner_ungrounded_kicker: 'sin fundamento',
    banner_ungrounded_text:
      'Esta respuesta no está anclada a código que el tutor haya leído de verdad, así que podría estar inventada. O el proyecto no lo cubre, o el tutor respondió demasiado pronto. Vuelve a preguntar, o apunta a un archivo, función o commit específico.',
    banner_off_target_kicker: 'fuera de foco',
    banner_off_target_text:
      'Esto está anclado al código, pero responde una pregunta distinta a la que hiciste. Vuelve a preguntar para redirigirlo a lo que querías decir.',
    banner_insufficient_evidence_kicker: 'evidencia insuficiente',
    banner_insufficient_evidence_text:
      'El tutor buscó, pero el proyecto no contiene lo suficiente para responder esto con confianza. Lo que haría falta está nombrado arriba.',
    banner_partial_kicker: 'respuesta parcial',
    banner_partial_text: 'Esta respuesta se interrumpió antes de terminar. Puede estar incompleta.',
    banner_fallback_kicker: 'sin respuesta',
    banner_fallback_text: 'El tutor no pudo producir una respuesta para esta pregunta esta vez.',
  },
}

export function pickLang(lang?: string | null): Lang {
  return lang === 'es' ? 'es' : 'en'
}

export function t(key: string, lang?: string | null): string {
  const l = pickLang(lang)
  return STRINGS[l][key] ?? STRINGS.en[key] ?? key
}
```

- [ ] **Step 2: Typecheck**

Run: `npm --prefix frontend run build`
Expected: `tsc -b` passes.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/cuaderno/strings.ts
git commit -m "feat(cuaderno-fe): two-locale chrome strings module + t()/pickLang"
```

---

## Task 6: wire the language through the components

**Files:**
- Modify: `frontend/src/pages/CuadernoPage.tsx`, `frontend/src/components/cuaderno/Cuaderno.tsx`, `frontend/src/components/cuaderno/GotItMarkers.tsx`, `frontend/src/components/cuaderno/frames/FrameDynamic.tsx`, `frontend/src/components/cuaderno/frames/FrameMidStream.tsx`

- [ ] **Step 1: Capture the meta language in `CuadernoPage.tsx`**

Add a state hook near the other `useState`s:

```typescript
const [currentQuestionLanguage, setCurrentQuestionLanguage] = useState<string | null>(null)
```

In the `case 'meta':` handler (lines 90-96), capture the language:

```typescript
      case 'meta':
        if (e.question_language !== undefined) {
          setCurrentQuestionLanguage(e.question_language ?? null)
        }
        if (!capturedSession) {
          capturedSession = e.session_id
          setSessionId(e.session_id)
          localStorage.setItem(SESSION_STORAGE_KEY, e.session_id)
        }
        break
```

Pass it to `<Cuaderno>` (find the `<Cuaderno ... />` invocation, add the prop):

```typescript
        questionLanguage={currentQuestionLanguage}
```

- [ ] **Step 2: Thread it through `Cuaderno.tsx`**

Add to the `Props` type:

```typescript
  questionLanguage?: string | null
```

Destructure it in the component signature (add `questionLanguage` to the props list), then pass the right language to each child. The live scenes use the meta language; the terminal scene uses the persisted frame language:

FrameMidStream (scene 'midstream'):
```typescript
  <FrameMidStream
    question={streamingQuestion || questions[questions.length - 1]?.question || '…'}
    tools={toolCalls}
    partial=""
    language={questionLanguage}
  />
```

Live FrameDynamic (scene 'writing'):
```typescript
  <FrameDynamic
    frame={{ question: streamingQuestion, blocks: partialBlocks }}
    onOpenCitation={setSidePanelFor}
    onAsk={onAsk}
    language={questionLanguage}
  />
```

Terminal FrameDynamic (scene 'frame') — pass the meta language as a fallback; the component prefers `frame.question_language`:
```typescript
    <FrameDynamic
      frame={activeQuestion.frame}
      onOpenCitation={setSidePanelFor}
      onAsk={onAsk}
      language={questionLanguage}
    />
```

GotItMarkers — restore-safe, prefer the persisted frame language:
```typescript
  <GotItMarkers
    value={activeQuestion.got_it}
    onSet={(v) => onSetGotIt(activeQuestion.position, v)}
    language={activeQuestion.frame.question_language ?? questionLanguage}
  />
```

- [ ] **Step 3: Localize `GotItMarkers.tsx`**

Add the prop + use `t()`. Full replacement:

```tsx
import { t } from './strings'

type Props = {
  value: 'got' | 'didnt' | null
  onSet: (v: 'got' | 'didnt') => void
  language?: string | null
}

export function GotItMarkers({ value, onSet, language }: Props) {
  if (value === null) {
    return (
      <div className="gotit">
        <span className="ask">{t('gotit_prompt', language)}</span>
        <button className="gotit-btn" onClick={() => onSet('got')}>
          <span style={{ color: 'var(--accent-2)' }}>✓</span> {t('gotit_got', language)}
        </button>
        <button className="gotit-btn" onClick={() => onSet('didnt')}>
          <span style={{ color: 'var(--accent)' }}>↻</span> {t('gotit_didnt', language)}
        </button>
      </div>
    )
  }
  if (value === 'got') {
    return (
      <div className="gotit">
        <button className="gotit-btn is-got">{t('gotit_marked_got', language)}</button>
        <span className="gotit-msg">
          {t('gotit_saved_pre', language)}
          <span style={{ color: 'var(--ink)' }}>{t('gotit_saved_mid', language)}</span>
          {t('gotit_saved_post', language)}
        </span>
      </div>
    )
  }
  return (
    <div className="gotit">
      <button className="gotit-btn is-didnt">{t('gotit_marked_didnt', language)}</button>
      <span className="gotit-msg">{t('gotit_didnt_msg', language)}</span>
    </div>
  )
}
```

- [ ] **Step 4: Localize `FrameMidStream.tsx`**

Add the prop + `t()` for "you asked" and "running…":

```tsx
import type { ToolRow } from '../../../types/api'
import { t } from '../strings'

type Props = {
  question: string
  tools: ToolRow[]
  partial: string
  language?: string | null
}

export function FrameMidStream({ question, tools, partial, language }: Props) {
  return (
    <>
      <div className="cua-question">
        <span className="label">{t('you_asked', language)}</span>
        <span className="q">{question}</span>
      </div>
      <div className="toolcalls" aria-label="LLM tool calls">
        {tools.map((t_, i) => (
          <div key={i} className={`row ${t_.state}`}>
            <span className="tag">
              {t_.state === 'done' ? '✓' : t_.state === 'error' ? '⨯' : t_.state === 'running' ? '◐' : '·'}
            </span>
            <span className="name">{t_.name}</span>
            <span className="args">{t_.args}</span>
            <span className="meta">
              {t_.state === 'done'
                ? `${t_.ms ?? 0} ms`
                : t_.state === 'error'
                ? 'failed'
                : t_.state === 'running'
                ? t('running', language)
                : 'queued'}
            </span>
          </div>
        ))}
      </div>
      <p className="cua-lead">
        {partial}
        <span className="streaming-caret" />
      </p>
    </>
  )
}
```

(Note: the map variable was renamed `t` → `t_` to avoid shadowing the imported `t`. "failed" / "queued" are micro-states; localize them too if desired by adding keys, but they are out of the named scope — leave as-is for now.)

- [ ] **Step 5: Localize `FrameDynamic.tsx`**

Make `STATUS_BANNER` a function of language (keyed strings), add the `language` prop, resolve `frame.question_language ?? language`, and localize "you asked" / "go deeper". Changes:

Replace the top-of-file `STATUS_BANNER` const (lines 4-25) with a language-aware builder that reads from `strings.ts`:

```tsx
import type { Block, Citation, Frame } from '../../../types/api'
import { CitationChip } from '../CitationChip'
import { t } from '../strings'

function statusBanner(status: NonNullable<Frame['status']>, lang?: string | null):
  { kicker: string; text: string } | undefined {
  const map: Partial<Record<NonNullable<Frame['status']>, string>> = {
    ungrounded: 'ungrounded',
    off_target: 'off_target',
    insufficient_evidence: 'insufficient_evidence',
    partial: 'partial',
    fallback: 'fallback',
  }
  const k = map[status]
  if (!k) return undefined
  return { kicker: t(`banner_${k}_kicker`, lang), text: t(`banner_${k}_text`, lang) }
}
```

Add `language` to `Props`:

```tsx
type Props = {
  frame: Frame
  onOpenCitation: (c: Citation) => void
  onAsk: (question: string) => void
  language?: string | null
}
```

In the component, resolve the language once and use it (replace `const banner = frame.status ? STATUS_BANNER[frame.status] : undefined`):

```tsx
export function FrameDynamic({ frame, onOpenCitation, onAsk, language }: Props) {
  const lang = frame.question_language ?? language
  const banner = frame.status ? statusBanner(frame.status, lang) : undefined
```

Replace `"you asked"` (line 60):

```tsx
        <span className="label">{t('you_asked', lang)}</span>
```

Replace `"go deeper"` (line 199, inside `BlockRender`'s `followups` case). Since `BlockRender` does not receive `lang`, pass it down: change the `blocks.map(...)` to forward `lang`, and add `lang` to `BlockRender`'s props. Concretely:

In `FrameDynamic`'s return, where blocks are mapped:
```tsx
      {blocks.map((b, i) => (
        <BlockRender key={i} block={b} onOpenCitation={onOpenCitation} onAsk={onAsk} lang={lang} />
      ))}
```

Update `BlockRender`'s signature and the `followups` cap:
```tsx
function BlockRender({
  block,
  onOpenCitation,
  onAsk,
  lang,
}: {
  block: Block
  onOpenCitation: (c: Citation) => void
  onAsk: (question: string) => void
  lang?: string | null
}) {
```
and in the `followups` case:
```tsx
          <div className="cap">{t('go_deeper', lang)}</div>
```

(The provenance note text — "predates grounding checks…" / "the reviewer was unavailable…" — is currently English chrome too. It is part of the answer-turn surface; localize it the same way by adding two keys to `strings.ts` and replacing `provenanceNote`. If kept minimal, leave it English and note it; the spec's named scope is the banners + you-asked + go-deeper + got_it. Recommended: localize it — add `provenance_legacy` / `provenance_unjudged` keys and use `t(...)`.)

- [ ] **Step 6: Typecheck + manual verify**

Run: `npm --prefix frontend run build`
Expected: `tsc -b` passes, vite build succeeds.

Manual (the real verification, since there is no FE test runner): with the backend running (`copyclip start` on a project, an API key set), ask a Spanish question and confirm the chrome ("preguntaste", "¿esto responde la pregunta?", "lo capté" / "no lo capté", "profundiza", and any banner) renders in Spanish; ask an English question and confirm English; reload and confirm a restored Spanish frame still shows Spanish chrome.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/CuadernoPage.tsx frontend/src/components/cuaderno/Cuaderno.tsx frontend/src/components/cuaderno/GotItMarkers.tsx frontend/src/components/cuaderno/frames/FrameDynamic.tsx frontend/src/components/cuaderno/frames/FrameMidStream.tsx
git commit -m "feat(cuaderno-fe): chrome mirrors the question language (got_it, you-asked, go-deeper, banners)"
```

---

## Final verification

- [ ] **Backend suite:**

Run: `python -m pytest tests/test_cuaderno_chrome_i18n.py tests/test_cuaderno_compositor.py tests/test_cuaderno_ask_stream.py tests/test_cuaderno_retry_recovery.py tests/test_cuaderno_persistence.py -q`
Expected: all PASS.

- [ ] **Full backend suite (no regression):**

Run: `python -m pytest -q`
Expected: all PASS (prior baseline: 605 passed, 3 skipped, plus the new chrome-i18n tests).

- [ ] **Frontend typecheck:**

Run: `npm --prefix frontend run build`
Expected: passes.

- [ ] **Microcopy pass (before merge):** run a `solace-wren` review over the `es` block of `strings.ts` and the backend `es` strings in `i18n.py` to tighten Venezuelan voice; apply edits.

---

## Self-review notes (spec coverage)

- Spec §5.1 carry the language (meta event + Frame field, same `detect_language`) → T1 (Frame field + persistence), T2 (`_seal`/`_fallback_frame` set it), T3 (meta event). §5.2 frontend strings module + components → T5, T6. §5.3 backend injected text localized → T2 (`i18n.py` + fallback), T3 (partial marker). §3.1 authoritative not frontend-detect → realized (the value flows from the backend; the FE never re-detects). §4 scope (answer-turn only; periphery English) → T5/T6 touch only the answer-turn components; empty state / Settings / breadcrumbs untouched. §6 unknown→en → `tr` (backend) and `pickLang`/`t` (frontend). §7 testing → backend pytest in T1-T3; frontend `tsc -b` + manual (no runner, by decision).
- Type consistency: `question_language` (snake_case) is the field on `Frame` and the `meta` event, backend and TS, throughout. `t(key, lang?)` / `pickLang` / `tr(key, lang, **kwargs)` signatures are stable across T5/T6/T2/T3. The FE `language?: string | null` prop name is consistent across GotItMarkers / FrameDynamic / FrameMidStream / Cuaderno.
- Deferred (named, not built): the UI-language setting for the periphery; localizing the `{reason}` internal phrases and the FrameMidStream "failed"/"queued" micro-states (optional); the solace-wren microcopy polish is a pre-merge step, not a code task.
```
