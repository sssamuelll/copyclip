# Cuaderno UI-Chrome i18n — Mirror the Question's Language

**Status:** Design (approved 2026-06-02) — ready for implementation planning
**Surface:** `src/copyclip/intelligence/cuaderno/` + `frontend/src/components/cuaderno/`
**Builds on:** the answer-quality specs (`2026-06-01`, `2026-06-02-judge-phase2`), which named UI-chrome i18n as the deferred follow-up; and the retry-recovery fix (PR #128), which added a `partial` marker literal.
**Author:** Samuel + Claude Code

---

## 1. Motivation

The cuaderno already mirrors the user's language in the *answer* — the model writes Spanish blocks for a Spanish question. But the **fixed UI chrome** is hardcoded English, so a Spanish answer is wrapped in English controls: `"you asked"`, `"does this answer the question?"`, `"I got this"`, `"I didn't"`, `"go deeper"`, and the status banners (`"not grounded"`, etc.). Observed live: a Spanish Q&A ("¿cómo funciona?" → Spanish answer) framed entirely in English chrome. This is the UI-chrome i18n every prior answer-quality spec deferred.

## 2. The blocker that shapes everything

The question's language **is** computed — `detect_language(question)` runs in `quality.py:84` (returns `es | en | unknown`) — but it is used once to decide a language retry and then **discarded**. It never reaches the frontend: `Frame` (`schema.py:140`) and its `verdict` carry no language field, nor does the TS `Frame` type (`api.ts:835`). So translating the strings is not enough; **step zero is carrying the detected question-language to the renderer.** There is no existing i18n scaffolding anywhere (greenfield); the detector serves exactly the `es`/`en` pair.

## 3. Goals

- The **answer-turn chrome** mirrors the question's detected language (`es`/`en`), live and on restore, with no flicker between the streaming and terminal renders.
- The chrome language is the **same authoritative value** the answer-quality gate used — one source, no second detector that can drift.
- `unknown` (and any absent value) falls back to **English**, matching the gate's permissive default.
- Two locales (`es`/`en`) via a tiny dictionary — **no i18n library**.

## 3.1 Decision: authoritative `question_language`, not a frontend re-detector

The chrome reads the language the **backend** detected (carried to the frontend), rather than re-detecting from `frame.question` in TypeScript. Rationale: single source of truth (the chrome matches the exact `es`/`en` that gated the answer's language), no duplicate detector to drift, and it covers `fallback`/`partial` frames (which carry no `verdict` but do carry a question). Cost: one `Frame` field + one SSE `meta` field, set from the same `detect_language(question)`.

## 4. Non-goals (out of scope — stay English; future "UI-language setting")

The chrome that has **no question to mirror** is out of scope and remains English: the empty-state / welcome (`FrameEmpty.tsx`), the composer placeholder, Settings / provider tooltips, breadcrumbs (`copyclip` / `cuaderno`), and the history-overlay header. Mirroring these would need a persisted UI-language preference — a separate feature, named here, not built. Also out of scope: any locale beyond `es`/`en` (the detector serves only that pair); the retry **directives** (`prompts.py`) are model instructions, not user chrome, and stay as-is.

## 5. Architecture

### 5.1 Carry the language (two carriers, one source)

`detect_language(question)` is the single source. It is surfaced in two places so both the live stream and a restored frame render correctly:

- **Live — the SSE `meta` event.** `iter_ask_events` already yields `{"type": "meta", "session_id"}` first (`ask_stream.py:41`). Add `"question_language"` to it (computed from the question there). The live mid-stream chrome (`FrameMidStream`) and the live terminal render read this — so the language is known from the first event, with **no flicker** (the stream and the sealed frame agree).
- **Restore — `Frame.question_language`.** Add `question_language: Optional[str]` to the `Frame` dataclass (`schema.py`), set on **every** terminal seal path — `answer`, `ungrounded`, `insufficient_evidence`, `off_target`, `partial`, `fallback` — from `detect_language(question)`. Persisted via `frame_to_dict` / `frame_from_dict` (default `None` for legacy frames). On reload, the renderer reads it. (Critically, the `fallback`/`partial` frames carry no `verdict` but their banners are exactly where Spanish is wanted — a `Frame` field reaches them; a `verdict` field would not.)

Both come from the same function on the same question, so they always agree. The TS `Frame` type gains `question_language?: string | null`; the live session state gains the meta value. Renderers resolve the language as `frame.question_language ?? metaLanguage ?? 'en'`, and `'unknown'` is treated as `'en'`.

### 5.2 Frontend strings module

A new centralized module (e.g. `frontend/src/components/cuaderno/strings.ts`): `STRINGS = { es: {...}, en: {...} }` plus `t(key: string, lang: string): string` where `t` falls back to `en` for `unknown`/missing/null. No dependency. Keys cover the answer-turn chrome only:

- got_it: the prompt (`"does this answer the question?"`), the buttons (`"I got this"` / `"I didn't"`), and the confirmations (`"marked: got this"`, `"saved to … this matters … ask anything else when ready."`, `"marked: didn't"`, `"where did it break? …"`) — `GotItMarkers.tsx:10–34`.
- `"you asked"` (`FrameDynamic.tsx:60`, `FrameMidStream.tsx:13`), `"go deeper"` (`FrameDynamic.tsx:199`), `"running…"` (`FrameMidStream.tsx:36`).
- the five `STATUS_BANNER` entries — kicker + body — for `ungrounded` / `off_target` / `insufficient_evidence` / `partial` / `fallback` (`FrameDynamic.tsx:6–23`).

`GotItMarkers`, `FrameDynamic`, and `FrameMidStream` consume `t(key, lang)`. (Block `kicker`s and the follow-up *items* are **model-generated** — already in the answer's language — and are not chrome.)

### 5.3 Backend injected user-facing text

Two literals the **code** injects (not the model) are localized by the question's detected language via a small `{es, en}` map:

- the fallback-frame text in `compositor.py:_fallback_frame` (`"I couldn't finish this turn — {reason}. …"`),
- the `partial` marker added in `ask_stream.py:_persist_partial` (`"This turn was interrupted (…). Re-ask to retry."`).

`{reason}` (e.g. "tool-call budget exhausted") is itself an internal phrase; localize the surrounding sentence and keep the reason as a short appended detail, or map the known reasons too (implementation choice — keep minimal).

## 6. Guaranteed vs hoped

- **Guaranteed:** given a question whose language the detector resolves to `es` or `en`, the answer-turn chrome renders in that language, identically live and on restore (both read the same persisted/meta value); `unknown` and legacy/absent → English; no new locale, no i18n library, no second detector.
- **Hoped / limited (named):** the detector is a heuristic (`es`/`en` orthography + stopword vote) — a genuinely ambiguous or very short question resolves `unknown` → English chrome (acceptable; the answer itself faces the same limit). The out-of-scope periphery (empty state, Settings, breadcrumbs) stays English until a UI-language setting exists.

## 7. Testing strategy

- **Backend (no LLM):** `frame_to_dict` / `frame_from_dict` round-trip `question_language`, defaulting absent → `None` (legacy); each terminal seal path sets it (answer / ungrounded / insufficient / off_target / partial / fallback) from `detect_language(question)`; the `meta` event carries `question_language`; the fallback / partial texts are Spanish for a Spanish question and English otherwise.
- **Frontend:** `t(key, 'es')` vs `t(key, 'en')` return the right locale and `t(key, 'unknown')` / `t(key, null)` fall back to English; `GotItMarkers` / `FrameDynamic` / `FrameMidStream` render the Spanish chrome when given a Spanish frame and English otherwise; restore (a stored Spanish frame) renders Spanish chrome.

## 8. Open questions

None blocking. Deferred by decision: the **UI-language setting** that would localize the out-of-scope periphery (empty state, composer placeholder, Settings/provider tooltips, breadcrumbs, history header); any locale beyond `es`/`en`. Implementation choice left open: whether to localize each known fallback `{reason}` phrase or keep it as an appended English detail (start minimal).
