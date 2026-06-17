# UI/UX Design Brief — Cuaderno Playground: Guided Step-Through

**For**: the design team
**Date**: 2026-06-16
**Owner**: Samuel
**Engineering spec (the "why" and the constraints)**: `2026-06-16-cuaderno-playground-stepthrough-design.md`
**Status**: brief — we want mockups and an interaction design, not code

> This brief asks you to design the **UI/UX** of one widget. Engineering has already locked the architecture (what runs, where, and why). Your job is the *reading experience*: how a developer walks through one function's execution and understands what it did. Everything in §6 ("What we're asking you to design") is genuinely yours to solve. Everything in §5 ("Hard constraints") is fixed — designing against it wastes your time.

---

## 1. Context in three sentences

CopyClip is a tool for staying attached to your codebase while AI writes most of it. The **cuaderno** is its conversational notebook: you ask a question, it answers grounded in your real code, and sometimes it answers with a **widget** instead of prose. One of those widgets is the **playground** — when you ask it to *run* a function, it spawns a live sandbox (a Marimo notebook in an iframe) anchored to that one real function from your codebase.

## 2. The problem we're solving

Today the playground is an **input → output box**: you give it a value, it shows `function(value) → result`, plus a collapsed source view. It tells you *what the function returns* but never *what it does on the way there*. The product owner's verdict: it "still isn't clear."

We're replacing that with a **guided step-through**: capture one real execution of the function, then let the developer **walk it step by step** — see the current line of code, and see every variable's value at that step. Mental model: Python Tutor (pythontutor.com), but anchored to one real function, living inside our editorial notebook, and at our scale (a small embedded band, not a full-screen app).

## 3. The user and the moment

A developer reading a function an AI wrote, who can't tell what it actually does from reading it. They're in the cuaderno, they asked "run this," and they want to *watch it execute* and follow the state. They are not configuring a debugger; they are reading a recording. Calm, legible, guided — not an IDE control panel.

## 4. The interaction model — states to design

The widget moves through these states. Design each one. The two new, design-heavy states are **Preview-call** and **Stepping**.

1. **Idle / invitation** — the function is named; an affordance invites the walkthrough. (Today this is a single "run example" button; the verb is changing — see §7 copy.)
2. **Preview-call** *(new)* — the cuaderno's model has proposed a concrete call, e.g. `resolve_function_ref(conn, 42, ref)`. We show it **before running**, and it is **editable**, because confirming will run the developer's real code (with possible real side effects). The user reads/edits, then confirms. This is the consent + correction moment. Design the proposed-call display, the edit affordance, and the confirm action.
3. **Spawning / capturing** — a brief "preparing…" while the function runs once and the trace is captured.
4. **Stepping** *(new, the heart of it)* — the captured walkthrough. Components in §6. The developer scrubs forward/back; the source line and the state panel update together.
5. **Truncated** — the trace hit the step cap (~1000 steps). Stepping still works for the captured portion; the UI must say *"stopped at step N — trace truncated"* honestly.
6. **Fallback** — the function can't be stepped (async, generator, or a call we can't construct). We fall back to today's input→output box with a one-line note explaining why.
7. **Raised** — the function threw with this input. The throw is the **final step** of the walkthrough ("here it threw: `KeyError: 'x'`"), not an error screen.
8. **Ended / evicted / error** — the runtime closed, another example took the slot, or spawn failed. (These exist today; keep them coherent with the new states.)

## 5. Hard constraints (fixed — please design within these)

- **The band is ~480px tall and full-width inside the notebook column.** The live region is `height: 480px` (`cuaderno.css:1051`). You may propose a *taller* frame for the stepping state if you justify it, but assume small by default. Source + state + scrubber must breathe in this space — this is the central layout challenge.
- **It renders inside a Marimo notebook in an iframe**, built from Marimo's native UI primitives in v1 (a slider, text, tables, an in-body panel). **No hover tooltips in v1** (the captured data is line-level, so there are no sub-expression spans to anchor a tooltip to). Hover-on-value is a later phase; do not design it into v1.
- **One composed widget, not a foreign window.** A context band (breadcrumb + citation + head) wraps the iframe so the running thing reads as part of the page (`PlaygroundWidget.tsx:28-52`). The state panel must live **in the widget body**, not in a docked sidebar that escapes our chrome.
- **Use the owned palette — invent no new colors.** The system is warm paper + one sienna accent + one rare slate-teal. There is **no cyan, no amber, no red** in this product. The tokens below are the whole vocabulary.

### The design system (real tokens, from `frontend/src/styles/cuaderno.css`)

| Token | Light value | Use |
|---|---|---|
| `--paper` | `#FAF6EC` | page background |
| `--surface` / `--surface-2` | `#F1EADC` / `#E7DFCC` | widget bands, panels |
| `--hairline` / `--hairline-soft` | `#D8CFB7` / `#E6DEC9` | borders |
| `--ink` … `--ink-4` | `#1B1814` → `#A39C90` | text, primary → most-dimmed |
| `--accent` | `oklch(0.56 0.13 45)` | **sienna** — the one accent (highlighted-row line number, `kind` tag) |
| `--accent-soft` | `oklch(0.56 0.13 45 / 0.12)` | **the current-line highlight** (existing `.code .hl` `:396`, `.file-code .row.hi` `:883`) |
| `--accent-ink` / `--accent-line` | `oklch(0.42 0.13 45)` / `…/0.34` | accent text, accent borders |
| `--accent-2` | `oklch(0.52 0.10 200)` | slate-teal — **kept rare** ("got it / didn't" only); do not spend it here |
| existing "removed" tint | `oklch(0.56 0.13 30 / 0.10)` | desaturated sienna-red in `.diff .rem` `:806` — the **only** "negative" ink we own |

- **Fonts:** `--font-mono` = JetBrains Mono (all code and values), `--font-ui` = Inter (chrome/labels), `--font-body`/`--font-display` = Source Serif / Newsreader (editorial prose). The widget head is 11px uppercase, `0.16em` tracking, `--ink-3` (`.widget-head` `:666`).
- **Existing patterns to reuse (don't reinvent):** `.tree` mono name/value rows with `.indent` (`:751-760`); `.diff` add/remove tinting (`:800-806`); the step counter wants the tabular-nums register already used in `.cua-top .session`; the existing widget chrome (`.widget-head`, `.widget-body`, `.playground-run`, `.playground-close`, `.playground-live-context`).

### Suggested state→ink mapping (a starting point, not a mandate)

- **current line**: `--accent-soft` background (matches the existing `.hl` convention).
- **value changed this step**: `--accent` ink (or bolder weight).
- **value unchanged**: dim to `--ink-3` / `--ink-4` so the eye lands on what moved.
- **exception / threw**: the existing desaturated `.diff .rem` sienna-red — never a new red.

## 6. What we're asking you to design (these are genuinely open)

This is the heart of the brief. Solve these:

1. **The 480px layout.** Source + state panel + scrubber + step counter, legibly, in a short band. Side-by-side columns? Source-over-state stacked? Tabbed (source ⇄ state)? A taller frame for this state only? We lean toward "source leads, state supports, scrubber controls" — but the composition is yours.
2. **The state panel.** One step's state is a list of `name → value` pairs. How do you show *changed vs unchanged* so the eye finds what moved? How deep — only the current frame's locals, or the whole stack (globals + caller frames)? (Default to current-frame locals; surface deeper state on demand.)
3. **Large values.** A `DataFrame`, a 10k-element list, a deep nested dict. We cap and summarize at capture (`list[5000]`, `DataFrame[1000×12]`). What does the panel *show* at the cap — a shape summary, first-N + "expand," a type tag? This is the single biggest readability risk; design the truncation affordance.
4. **Step explosion.** A 12-step trace and a 600-step trace are different design problems. For long traces, design "collapse unchanged steps" / "jump to next change" / fold repeated loop iterations — so the scrubber isn't a 1px-per-step blur.
5. **The scrubber + counter.** Forward/back, a "step 14 / 87" indicator (tabular-nums, in the head beside the close button — don't add a new strip), and how a user jumps around a trace.
6. **The preview-call moment (state 2).** How the proposed call is shown and made editable, how "this will run your real code once" reads without alarming, and how confirm/edit/cancel sit together.
7. **The honest-limit copy.** Where and how the UI says "steps through your Python; library calls appear as one step," and the truncation / fallback / threw notes — calm, not apologetic.

## 7. Microcopy (proposed — final pass goes through our copy system)

These are starting strings, bilingual (the product ships `es`/`en`; see `frontend/src/components/cuaderno/strings.ts`). Final microcopy is a `solace-wren` pass; treat these as intent.

| Key | es (proposed) | en (proposed) | Note |
|---|---|---|---|
| invitation breadcrumb | `Recorre {name} paso a paso` | `Step through {name}` | replaces today's `Ejecuta {name} con un ejemplo` (`compositor.py:162`) — the current verb promises *output*, which is half of why it felt "lost" |
| step affordance | `Recorrer` | `Step through` | replaces `correr ejemplo` / `run example` |
| preview-call lead | `Voy a recorrer esta llamada:` | `I'll step through this call:` | above the editable call |
| run-real-code note | `Corre tu código real una vez, con sus efectos.` | `Runs your real code once, side effects included.` | calm consent line |
| pure-Python limit | `Recorre tu Python; las llamadas a librerías son un paso.` | `Steps through your Python; library calls appear as one step.` | the C-extension honesty note |
| truncated | `Detenido en el paso {n} — traza truncada.` | `Stopped at step {n} — trace truncated.` | |
| fallback (async/gen/uncallable) | `Esta función no se puede recorrer paso a paso todavía — aquí está su entrada y salida.` | `This function can't be stepped through yet — here's its input and output.` | |
| step counter | `paso {n} / {total}` | `step {n} / {total}` | tabular-nums |

## 8. Reference mock — intent, not prescription

This ASCII sketch communicates *what we mean*, not *how it should look*. The composition, the truncation affordance, the large-value treatment, and the long-trace handling are yours to design.

```
┌ playground · resolve_function_ref ─────────── step 4 / 9 ─┐
│ Step through resolve_function_ref                          │   ← breadcrumb (the new verb)
├──────────────────────────────────┬─────────────────────────┤
│ 255 def resolve_function_ref(...) │  STATE (step 4)         │
│ 256   qualname = ref.qualname ... │  qualname  'Foo.method' │   ← changed: --accent ink
│▶257   if "." in qualname:         │  parent    None         │
│ 258     head, tail = ...          │  conn      <Connection> │   ← opaque type (skip-repr)
│ 259                               │  ref       FunctionRef… │   ← large: summary + expand
├──────────────────────────────────┴─────────────────────────┤
│  ◀ ───────────●────────────── ▶     step 4 / 9              │   ← scrubber + counter
└────────────────────────────────────────────────────────────┘
  Steps through your Python; library calls appear as one step.
```

(Current line on `--accent-soft`; the state panel is **in-body**, mono, dimming what didn't change.)

## 9. Deliverables we'd love from you

- Mockups for each state in §4 (especially **Preview-call** and **Stepping**).
- A solved **480px layout** (and a recommendation on whether the stepping state needs a taller frame).
- The **large-value / truncation** treatment and the **long-trace** (step-explosion) treatment.
- Light + dark (the system themes via `.theme-dark`; tokens above have dark values).
- Any motion/transition between steps that aids comprehension without distracting.

## 10. Explicitly out of scope for this design

- Hover-on-value tooltips and a heap/pointer diagram — those belong to a later phase (a custom client-side renderer) and depend on richer captured data we don't have in v1. Don't design them in.
- A live "step in/over/out" debugger control surface — we are designing a *reader over a recording*, not a debugger.
- The backend (how the trace is captured, the caps, the contract) — that's the engineering spec; you don't need it to design the surface, but it's there if you're curious.
