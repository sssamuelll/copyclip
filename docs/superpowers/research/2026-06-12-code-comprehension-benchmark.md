# Code-Comprehension Strategies: Benchmark + Honest Build Plan for the CopyClip Cuaderno

> Produced 2026-06-12 by a 21-agent roster workflow: 6 research lanes (cognitive science of program comprehension, learning science, practitioner technique, tooling landscape, the AI-generated-code comprehension gap, visualization) + 3 substrate-grounding lanes → a 14-strategy scored benchmark → a 9-persona council → Axiom-0. 51 raw strategies clustered into 5 families. The ranking below is the **council-corrected** order, not the raw 1–5 totals.

## 1. TL;DR

What actually builds code understanding is **generative friction**: the human produces an answer — a guess, a one-sentence why, a predicted blast radius — *before* the tool reveals anything, and the tool's only job is to set the cited ground truth beside that answer and stay silent about the human's mind. Reception (the tool explaining fluently) is the failure mode the whole product must resist; a tidy explanation *feels* like teaching while the human stays lost. But the council is unanimous on a correction the raw scores missed: the strategies that are safe here are not the ones with the best learning-science pedigree — they are the ones whose **claim never reaches past what the substrate witnessed** (a cited path+line, a logged click, an elapsed time). **The single wedge CopyClip should own is re-owning accepted AI code through cited exposure: walk the slice, recover the decision, flag the unreturned-to burst — and where the ledger is silent, say so.** The signature move is the vertical slice whose honesty holds *by construction* because the slice **is** its citations; the sharpest sentence in the product is `"no recorded rationale; this was accepted, not decided."`

## 2. The benchmark

Ranking below is the **council-corrected** order, not the raw 1–5 totals. The raw benchmark crowned the playground-prediction loop (#1, 4.65); every one of the nine roles demoted it because its "computed reveal" has no capture-to-citation path, and promoted the cited/witnessed strategies. Effectiveness/didactic-depth scores are shown but explicitly **discounted** — they import credibility from learning-science studies on other populations into a substrate that cannot observe whether recall occurred (Voronov, Axiom-0).

| # | Strategy (honest name) | Cluster | Effect. | Didactic | Practic. | Substrate fit | AI-burst rel. | Verdict |
|---|---|---|---|---|---|---|---|---|
| 1 | **Walk the path** — vertical-slice tracing, every hop cited | tracing | 5 | 4 | 5 | **5 (real)** | 5 | **BUILD FIRST.** Honest by construction; fully wired; cheap; language-universal. The spine. |
| 2 | **"Accepted, not decided"** — decision/archaeology intent recovery + absence-of-rationale flag | scaffolding | 4 | 4 | 5 | 5 | 5 | **BUILD.** The wedge in one cited sentence. Needs a deterministic absence-gate (today it's prompt-only). |
| 3 | **Hasn't-been-back** — Pulso over-trust / last-contact atom | social | 4 | 2 | 5 | 5 (enforced) | 5 | **BUILD as the entry cue.** Only strategy whose honesty is sealed in code, not prose. Launches #1/#4. |
| 4 | **What else does this touch?** — blast-radius predict-then-reveal | tracing | 4 | 5 | 5 | 5 | 5 | **BUILD.** Generative friction with zero playground dependency. Reveal is cited static topology. |
| 5 | **The plan, reassembled** — delocalized-plan stitching across a burst | tracing | 4 | 4 | 4 | 4 | 5 | **BUILD (capped).** Each fragment's membership must rest on a witnessed edge, never narrative glue. Budget-bounded. |
| 6 | **Say it back** — self-explanation/teach-back, diffed against cited anchors | active-recall | 5 | 4 | 4 | **3** | 5 | **DEFER to Phase 2.** Strongest *persistable* signal — but has no column to live in today. Gated on a witness ledger. |
| 7 | **Say why, then check** — seed-the-hypothesis + tests-first | scaffolding | 4 | 3 | 5 | 4 | 5 | **BUILD (folded into #2/#1).** Lead hypothesis MUST come from a real decision/commit, never a paraphrase. |
| 8 | **Name the chunk** — ≤4 named cited spans of a long function | scaffolding | 4 | 3 | 5 | 5 | 3 | **BUILD (light).** Pure block reuse; the antidote to scrollable-tour theater. Pair one chunk with a predict gesture. |
| 9 | **Name vs behavior** — beacon/plan-naming + naming-honesty gap flag | scaffolding | 4 | 3 | 4 | **3** | 5 | **DEFER.** Honesty bounded by tree-sitter edge-set completeness (unverified). Misresolved edge = false accusation. |
| 10 | **Guess first** — forced prediction over the anchored playground | active-recall | 5 | 4 | 4 | **2 (honest)** | 5 | **DEFER to Phase 3.** Reveal channel has no result-to-citation path. Ships theater or ships nothing novel today. |
| 11 | **How does this actually work?** — IOED mechanistic descent | active-recall | 4 | 5 | 3 | 3 | 5 | **FOLD into #1.** Strip the self-rating gesture entirely; what remains is #1 with a question. |
| 12 | **Call order (static)** — dual-coding subgraph / CallersTree, refuse-gate | visualization | 3 | 3 | 4 | 5 | 4 | **GLOBAL LAW, not a strategy.** One visual per frame, ≤25 nodes or degrade to CallersTree, drill-down-or-don't. |
| 13 | **Less help where you've been before** — ZPD/scaffolding meta-router | scaffolding | 4 | 4 | 3 | **2** | 4 | **DO NOT BUILD as a router.** Keep only the literal echo of witnessed acts; never infer a level. |
| 14 | **Haven't touched this since `<date>`** — spaced re-surfacing | social | 3 | 2 | 4 | **2** | 5 | **COLLAPSE into #3.** No `got_it_at` means no clock to space on. The honest part *is* #3. |

## 3. Why these win

The top cluster — **active-recall and the generative shells of tracing** — wins because of one cognitive mechanism, but the council insists on the *right* statement of why.

The learning-science literature is real: the **testing effect / retrieval practice** (Roediger & Karpicke) shows that generating an answer durably outperforms re-reading; **pretesting** (Richland, Kornell, Kao) shows that a *wrong* guess before the reveal primes encoding of the correct value; **self-explanation** (Chi) and the **Feynman/teach-back** family show that articulating *why* surfaces the gaps a fluent read papers over; the **Illusion of Explanatory Depth** (Rozenblit & Keil) shows that people rate their mechanistic understanding far above what a forced "how" descent can sustain; **desirable difficulties** (Bjork) explain why the friction is the feature, not a UX cost. Accepted AI code is the perfect IOED trap: it reads fluent, passes tests, looks clean — the human never wrote the beacon, so they never built the model, yet the fluency simulates one.

**But the council's load-bearing reframe (Voronov, Null Vale, Axiom-0): generation is not safe because it teaches better — you cannot observe that it taught.** It is safe because when the human *generates*, the tool's only honest job is to put the cited ground truth next to the guess and **say nothing about the gap**. The defense against comprehension-theater is not "make the human generate." It is "never speak about the human's interior." Generation is merely the interaction shape that makes that silence *natural* — the human's own guess, sitting beside the cited fact, does the pedagogical work the tool is forbidden to narrate. Defend the top strategies on **honesty-completeness**, not effectiveness, and they become unkillable; defend them on imported effectiveness and a skeptic dismantles them by pointing at `got_it`.

This is why the *cited/witnessed* strategies (Walk the path, Accepted-not-decided, Hasn't-been-back) outrank the *generative-but-uncaptured* ones (Guess first, Say it back) **on this substrate**: the slice IS the citations, the archaeology IS the commit, the Pulso atom IS elapsed time. They hold by construction. The generative strategies are only as honest as the channel that captures the generated answer — and that channel is not built.

## 4. The honesty line — what CopyClip must NEVER do

**The invariant (Axiom-0):** *A measurement may speak exactly as far as its substrate has witnessed, and not one symbol further.* The system has exactly **one closed loop** — the grounding loop (`quality.py:assess` seals `ungrounded` when a code claim's citations are disjoint from read paths). It measures *is this claim true of the code*. It has **no** loop on *did this land in a head* — and the honesty doctrine "exposición, no autoría" is not a pedagogy, it is the confession that the second loop was never built and the design chose not to fake it. Every safe strategy keeps its claim inside what the system touched; every forbidden one reaches past it. Null Vale's grammar collapses it: **CITE and WITNESS are incorruptible verbs; INFER and NARRATE open the theater.**

CopyClip must **NEVER**:

- **Narrate a computed or executed value the system did not compute.** While the result-capture path is absent (the playground floor emits a click-to-run *descriptor* and never feeds an executed value back to a citation; `_floored_frame` can reseal an un-runnable run-request as `status='answer', grounded=True` — `compositor.py:166–223`), any "reveal" must be a cited static value (`read_file` + `grep_symbols`) **explicitly labeled not-executed**. A narrated execution under playground chrome is the fluent-summary failure with execution-grade authority — the single worst object this system could ship.
- **Convert any guess-vs-computed gap, self-rating, teach-back diff, or prediction-vs-graph delta into a number** — stored, aggregated, shown, or per-file. The instant a generated answer becomes a queryable score, you have rebuilt the W4-3 comprehension score the roster unanimously refused. Log the **event**; never score the **human**.
- **Route teaching strategy off `got_it`/ratify/last-contact as if they witness understanding** (the ZPD router). They witness review, recency, and a self-report click — never comprehension. `got_it` is last-write-wins, no `got_it_at`, no history, no file FK (`persistence.py:97`); a `didnt`→`got` recovery is *invisible*. The witnessing channel's resolution must be at least as fine as the claim routed on it (Halberg's orchestration law) — and a three-state, timestamp-less flag cannot drive a fine-grained sequencer. No "we detected your level," no "your memory decayed to 0.4."
- **Render static call topology as observed runtime.** SequenceDiagram and GraphSubset stamp *structure*, not execution. The label must read **"Call order (static)"** in the widget *title*, not a footnote — and ideally be enforced structurally, because today it is fail-open model discretion.
- **Fabricate a rationale when the ledger is silent.** No gate enforces the absence-flag today; a model that paraphrases a plausible purpose passes every existing `quality.assess` check. A confident invented "why" is the highest-authority comprehension-theater — it teaches a false history with the tool's credibility. Silence must render as `"no recorded rationale; accepted, not decided."`
- **Cross from "the FILE is stale" to "your MENTAL MODEL is stale."** `prompts.py:143` already forbids "you don't understand X." NULL last-contact is a neutral third state, never low comprehension. One adjective crosses the line into the refused score.
- **Assert a plan-name, chunk-name, or fragment-grouping the human now *recognizes*** — or one whose membership rests on model inference rather than a witnessed structural edge (shared symbol, call edge, decision_ref). Naming a view the human did not assemble, as if they did, installs a wrong model with the tool's authority.
- **Name a feature for a mind-state** (Wren). No "understand," "mastery," "learn," "grasp," "get it," "comprehension," or "review." Name the human's witnessable **action** or the tool's cited **artifact**.

## 5. Implementation roadmap (phased)

Ordered by ship-readiness per Cassian/Lyra: cited-by-construction first, generative-but-uncaptured behind the substrate that would witness it.

### Phase 1 — Ships this week (cited by construction, zero new infra)

**① Walk the path** *(vertical-slice tracing — the spine)*
- **Reuses:** `get_callees` → `get_module_graph` → `find_tests` (all live, `anchor.py`); emits an ordered `citation_stack`, one citation per hop (path+line). Anchor the entry on a `get_last_contact` file so the human re-walks the exact AI burst.
- **New substrate:** none. (Drop the SequenceDiagram cap — it duplicates the stack's edge-set in a weaker visual that reads as runtime. The slice carries itself.)
- **Honesty gate:** the slice IS the citations — nothing to fence. Add **one predict-the-next-hop gesture** so at least one hop flips from viewing to responding (Naps engagement dial). Cap slice depth so a hot symbol doesn't fan into a token-draining tour and hit the round-8 `CLOSING_DIRECTIVE`.
- **Build cost:** **cheap.**

**② "Accepted, not decided"** *(decision/archaeology intent recovery)*
- **Reuses:** `get_decisions`, `git_archaeology`, `git_blame`/`git_log`/`git_diff`, `commits.ai_attributed` (`_AI_COAUTHOR_RE` trailer); emits a `citation_stack` "this exists because…" capped by **one** honesty-gap `callout`.
- **New substrate:** a **deterministic absence-gate** — modeled on the existing `_floored_frame` floor pattern: *ledger silent → system stamps `"no recorded rationale; accepted, not decided"`*. This is the only genuinely new build in Phase 1 and it is mandatory; without it the wedge's signature move is prompt-hope. **Also fix the `decision_history` `CURRENT_TIMESTAMP` (local) vs ISO-8601 UTC mismatch** before shipping, or the "why" chain orders backwards and narrates a false causal history with full citation authority.
- **Honesty gate:** never invent a why; recovering recorded intent is not the human holding it.
- **Build cost:** **cheap** (anchors) + **moderate** (the absence-gate + timestamp fix).

**③ Hasn't-been-back** *(Pulso over-trust / last-contact entry cue)*
- **Reuses:** `build_last_contact` (`pulso.py`, already fenced from comprehension in code + `prompts.py`), `commits.ai_attributed`; emits a silent-on-absence cited `callout` + ONE followup *"want to re-derive this one?"* that launches ② or ④ (never the playground).
- **New substrate:** none — but gate the surfacing on **analysis recency**, because `analysis_file_insights` is a batch snapshot and `last_human_ts`/heat are recomputed only for churn-active `blame_candidates`; otherwise it fires on a file the human revisited yesterday.
- **Honesty gate:** the FILE is stale, never the mind. NULL = neutral third state.
- **Build cost:** **cheap.**

### Phase 2 — Generative friction without the playground

**④ What else does this touch?** *(blast-radius predict-then-reveal)*
- **Reuses:** a `followups` block ("if you changed this signature, which call sites break?"), then `get_reverse_dependents`/`get_callers` → a single `GraphSubset` + `citation_stack` of the **real** cited dependents; `find_tests` predicts which tests *should* fail; `git_archaeology`/`get_decisions` surfaces a constraining past decision.
- **New substrate:** none for the reveal. The guess-vs-graph gap is a **witnessed prediction event**, logged, never scored. (Two-state "change-it-and-see" perturbation is OUT — `playgroundSlot` is single-slot; relaunch evicts the baseline.)
- **Honesty gate:** reveal is cited static topology, NOT runtime. A good guess proves the prediction matched *these cited edges*, never "you understand the blast radius."
- **Build cost:** **cheap.**

**⑤ The plan, reassembled** *(delocalized-plan stitching)* + **⑥ Say it back** *(teach-back)*
- **Stitching reuses** `get_reverse_dependents`/`get_callers`/`get_callees` + `grep_symbols` + `get_last_contact` into one cited `citation_stack`. **Gate:** each fragment's membership must rest on a **witnessed edge** (shared symbol, call edge, decision_ref) checked structurally — cut the narrative-glue path. Cap file-count to survive the 8-round budget.
- **Say it back** is the strongest *persistable* comprehension signal — but it **needs a new column** (the human's typed text has nowhere to live; `cuaderno_questions` has only `got_it`). This is the **append-only witness-event ledger** (`turn, file/symbol, event_kind, timestamp` — the deferred pulso-v02 work). Until it exists, ⑥ cannot persist its own active ingredient. **Gate:** speak ONLY to the cited mismatch (`claim-text` vs `behavior@line`), e.g. "your sentence did not mention the early-return at L42" — never grade, never "you misunderstand," never correct into agreement.
- **Build cost:** stitching **moderate**; teach-back **moderate + new substrate (witness ledger)**.

### Phase 3 — Gated on real execution capture (issue #88)

**⑩ Guess first** *(forced prediction over the anchored playground)*
- **Blocked on:** a **result-capture-to-citation** path. `marimo_runner.py` exists and is wired, but the floor emits a click-to-run descriptor and **never feeds an executed value back as a citation**; there is no `settrace` branch-label capture in `src`; execution is async, human-initiated, after the frame seals; and the runner is Python-only (no Go/Node/Rust path, so its AI-burst universality is false outside Python). Until the executed value flows back to a cited artifact, the "reveal" is a static read — which IS strategy ② wearing a playground costume.
- **Do not** wire a predict gesture to a button that errors or to a narrated value. The prediction shell is a one-line wrapper to bolt on *once* execution-capture lands.
- **Build cost:** **expensive (blocked).**

## 6. What we are NOT building

- **The ZPD / competence meta-router (#13)** — routes fine-grained pedagogy off a three-state, timestamp-less, history-less, file-less `got_it`; would either be uselessly coarse or fabricate the un-witnessed competence model the doctrine forbids. Keep ONLY the literal echo: "because you marked got / because you ratified / because you haven't returned." Never "we detected your level."
- **Spaced re-surfacing as a spacing curve (#14)** — no `got_it_at` means "previously got" cannot be dated, so "expanding intervals" has no anchor. The honest part is the witnessed-recency surfacing, which is already #3. Collapse it in.
- **IOED self-rating gesture (#11)** — the only novel element is a 1–5 self-rating the doctrine forbids storing or comparing; you'd build UI for a signal you must immediately discard. Keep the mechanistic descent, fold it into #1 as a "what happens if the token is expired here?" followup.
- **The playground "computed reveal" today (#10)** — no result-to-citation path; ships theater or ships nothing novel. Defer to Phase 3.
- **Name-vs-behavior gap flag (#9) as a near-term build** — honesty bounded by tree-sitter `symbol_edges` completeness, which is an unverified static approximation; a missed edge fails silently (false-clean), a misresolved edge accuses a wrong line with a real citation. Defer until edge-set membership is verified.
- **SequenceDiagram cap on the slice (#1's bundle)** — duplicates the citation_stack's edges in a weaker visual that reads as runtime. Cut it.
- **Any second visual or second callout per frame** — the callout is the one emphasis channel and five strategies want it; fire more than one and it becomes wallpaper. One visual per frame, ≤25 nodes or degrade to `CallersTree` (#12 as a **global law**, not a strategy).
- **Two-state perturbation / "change-it-and-see"** — `playgroundSlot` is a single global slot; relaunch destroys the baseline. There is no compare surface.

## 7. Open questions

- **Lyra's uncomfortable question:** *Is it worth a sprint to build the witness-event ledger (`got_it_at` + append-only `turn/file/event_kind/timestamp`) at all?* It is the precondition for the entire active-recall family (Say it back, the guess-gap, honest fading). But the moment that ledger exists, it is **one refactor away** from being read back as a per-file comprehension score — the exact W4-3 artifact the roster refused. The substrate's *current inability* to persist these signals is the only thing structurally protecting the doctrine, and absences get filled. Do we build the channel and defend the discipline by prompt + review forever, or do we accept that the most defensible comprehension signal in the system (the human's own typed words) **stays unpersisted by design** — keeping the second loop honestly open rather than dishonestly half-closed?
- **The join spine:** `cuaderno_sessions` keys on `project_root` TEXT, insights/risks on integer `project_id`, `cuaderno_questions` has no file/symbol FK. Every "anchor on `get_last_contact` files" claim assumes a `turn → file → burst → decision` identity spine the schema does not persist. Building it is the precondition for the wedge's universality across bursts. Is it Phase-0?
- **The withhold primitive:** the renderer is a single top-down scroll with no held region — a "pretest" prints above its own answer key, and the only free-text surface is the global ask bar. Do the generative strategies get a real in-frame curtain + guess-capture, or do we ship only the strategies whose visual form already IS their evidence until the surface earns one?
- **Enforcement vs. prompt-hope:** the absence-of-rationale flag, the "static call order" label, and the no-grade teach-back rule are all currently model discretion (fail-open). Which of these can be sealed in a deterministic gate (modeled on `_floored_frame`), and which must remain prompt-level — and is a prompt-level honesty claim ever shippable for a load-bearing gate?
- **Batch-snapshot freshness:** Pulso/risk/heat read a batch-written DB with no continuous re-analysis. What is the minimum analysis-recency gate before a "you haven't returned since `<date>`" callout is allowed to fire?
