# Pulso v0.2.1 — "Last visit" (kickoff)

**Fecha:** 2026-06-11
**Estado:** Ratificado por Samuel tras consejo del roster + Axiom-0 (workflow `pulso-v02-council`).
**Sigue a:** Pulso v0.1 (#161-#165, "Last contact"). **Extiende:** `intelligence/pulso.py`.

---

## 0. El invariante (Axiom-0, v0.2)

> **Un testigo da fe de su acto; el resto es el sistema hablando en nombre del humano.**

Avanza el invariante de v0.1 una capa: el substrato atestiguó **actos** (clics, preguntas, cambios de estado), nunca **holdings** (comprensión). Una métrica solo puede hablar la mitad atestiguada (el acto), nunca la inferida (comprensión), y debe cargar su distancia-al-referente en su propio nombre y forma.

## 1. Lo que el consejo corrigió (unánime)

**El substrato del cuaderno NO contiene comprensión.** Registra la relación humano↔*sistema* (actos contra una interfaz), no humano↔código. Un score de comprensión es **W4-3 una capa arriba, con un disfraz más fino** — rechazado.

Los tres actos de testigo son tres verbos distintos, rankeados **ratificar > preguntar > got_it**, anti-correlacionados en autoridad-vs-precisión (Voronov) — **nunca se promedian en un escalar**:

- **`got_it='got'`** — auto-reporte, **sin timestamp propio** (`set_got_it` no escribe `got_it_at` → decay incomputable), un loop cerrado que mide la persuasión del tutor. La cara honesta es **`'didnt'`** (confesión contra interés). → **diferido**.
- **Preguntas** — rastro de *ausencia* (uno pregunta porque NO lo tiene); honesto solo como recencia de atención. → **diferido**.
- **Ratificación de decisión** — el testigo más fuerte y **ya event-shaped + timestamped** (`decision_history`, append-only). El único shippable honesto hoy.

## 2. Decisiones ratificadas (Samuel, 2026-06-11)

**A. v0.2 = "Last visit", no un score de comprensión. ✅**
Extender el reloj de contacto de v0.1 con la ratificación de decisión como **segundo reloj datado de "vuelta del humano"**. Recencia + review, **NUNCA comprensión**. Diferir got_it (solo la cara `'didnt'` luego) y preguntas; rechazar el score de comprensión (inconstruible honestamente desde este substrato).

**B. Ship sobre el substrato de hoy. ✅ (Cassian/A, sobre Richter/B)**
Construir sobre lo que hay: `decision_history` filtrado a `action='status_change'` (la ratificación humana vía DecisionConfirm; `created`/`ref_added`/`link_added` son de sistema) + `decision_refs` **directos** (`ref_type='file'`, `ref_value=path`), NUNCA los globs de `decision_links.target_pattern`. Diferir la instrumentación (un `witness_events` ledger, `got_it_at`) hasta admitir got_it/preguntas. Ganar la siguiente lección con datos reales.

## 3. Arquitectura lockeada

1. **Un acto solo da fe de su verbo.** La ratificación atestigua "el humano autoró un estado sobre una decisión ligada a este archivo en fecha T" — nunca "comprende el archivo". El nombre debe sostener el gap.
2. **Composición en el `max(anchor)` existente, no un substrato nuevo** (Cassian). `contact_anchor = max(último_commit_humano, última_ratificación)`. Mismas reglas de silencio de v0.1 (ausencia → None, nunca 0).
3. **Solo `decision_refs` directos** (identidad), no `decision_links` globs (fuzzy → sobreclamo).
4. **Vocabulario honesto** (Wren): "Last visit" / acto "ratified"; jamás "understood"/"in sync"/"owned". Línea-confesión: *"A visit proves you were here, not that you understood."*
5. **No promediar los tres actos en un escalar** — cuando entren got_it/preguntas, serán eventos datados+tipados, no pesos.

## 4. El plan (v0.2.1, un PR)

- `pulso.py · _last_ratified_decision(conn, project_id, path)` → `MAX(decision_history.created_at)` de decisiones con `action='status_change'` y un `decision_refs(ref_type='file', ref_value=path)` directo. None si no hay.
- `build_last_contact`: computar `last_review`; el ancla de "vuelta" pasa a ser `max(last_human_commit, last_review)`; misma regla de silencio (si la última vuelta ≥ la ráfaga → silencio). Añadir `last_contact_source: 'git' | 'decision' | None` y `reviewed_days` (nullable). Las claves existentes (`last_contact_days`, `ai_burst_days`, `never_human_touched`) mantienen forma; `last_contact_days` ahora también cierra el gap en una ratificación.
- `anchor.get_last_contact` + `prompts.py`: superficie "Last visit" — un commit O una decisión ratificada cuentan como vuelta; "ratified" es el más firme (acto de autoría); sigue siendo tiempo/review, **nunca comprensión**.
- **DoD:** ratificación-tras-ráfaga rompe el silencio; ratificación-antes no; `max()` elige la más reciente entre git/decisión; ausencia → None; ningún string de salida contiene "comprehen"/"understood". `pytest -q` verde.

## 5. Diferido (guard de scope)

- **`got_it`** — necesita un `got_it_at` antes de poder hablar honesto; cuando entre, solo la cara `'didnt'` como marcador de "flagged-for-revisit", nunca `'got'` como comprensión.
- **Preguntas** (engagement = rastro de ausencia) — recencia de atención, evento aparte.
- **El score de comprensión** — NUNCA (inconstruible desde este substrato).
- **El `witness_events` ledger unificado** (Richter) + instrumentación (`got_it_at`, actor en `decision_history`) — cuando se admitan got_it/preguntas.
- **Curva de decay dedicada** — el reloj ya decae solo (los días crecen).
