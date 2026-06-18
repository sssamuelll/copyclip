# Pulso — el arco de la métrica honesta (kickoff)

**Fecha:** 2026-06-11
**Estado:** Ratificado por Samuel (2026-06-11) tras consejo del roster + Axiom-0.
**Issue:** #152. **Consejo:** workflow `pulso-council` (7 personas + Axiom-0), 2026-06-11.
**Precedente que NO se repite:** W4-3 (un signal que renderizó ~0 en todas partes porque leyó la columna muerta).

---

## 0. El invariante (Axiom-0)

> **Una medición solo puede hablar hasta donde su substrato ha atestiguado; más allá de esa línea, todo número es la opinión del sistema con el nombre del humano puesto.**

Todo lo de abajo es una proyección de este eje: la distancia entre el *referente* de una métrica y el *rastro que sobrevive en el substrato*. Distancia cero → honesto. Distancia >0 sin nombrar → sobreclamo, y sobreclamo renderizado con confianza ES W4-3.

## 1. Lo que el consejo corrigió de #152 (unánime)

1. **El trailer NO es enhancement — es la PRECONDICIÓN.** Verificado en vivo: `agent_line_ratio > 0` es **0/203** archivos (el cadáver de W4-3: Samuel commitea el trabajo de la IA bajo su propio nombre, así que blame-author nunca lo distingue). `Co-Authored-By: Claude` está en **123/200** commits y el ingest no lo lee (`git log --pretty=%H|%an|%ad|%s` — solo el subject; el trailer vive en el body). Sin el trailer, "time-since-human-touch" lee el cadáver → el gemelo isomorfo de W4-3, pero **"invisiblemente verde"** (Richter): reporta fuga-baja justo cuando la fuga es máxima, porque la ráfaga de la IA refresca `last_human_ts` (lleva el nombre de Samuel).
2. **La comprensión no se deriva de git — se atestigua** (Voronov). `time-since-touch` y `burst-recency` prueban *recencia*, no comprensión. Una métrica de comprensión derivada (a) sobreclama y (b) viola el propio test de mediación del wedge ("nunca una capa-agente que conecte las ráfagas por él"). El único signal honesto de comprensión es un **acto de testigo** que el humano realiza.
3. **La forma es errónea para el wedge** (Richter/Voronov). Un gap es un verbo sobre un intervalo (dos extremos, duración, evento de cruce). Un escalar por archivo no puede representarlo. El wedge real es un **ledger de transiciones ráfaga→gap→reconexión**, no un número. → v0.2.
4. **`decision_gap` (200/203) y el cadáver de blame son el mismo problema de substrato** (Vale). Los factores de autoría (`agent_authored_ratio` 0.22 + `review_staleness` 0.15 = 0.37) abandonan el denominador en ~87% de los archivos (blame está capado a `churn.most_common(25)`), dejando que `decision_gap` llene el vacío. Reweighting es whack-a-mole: `test_evidence_gap` (también binario 0/100) satura después.

## 2. Decisiones ratificadas (Samuel, 2026-06-11)

**A. v0.1 = el átomo "Last contact". ✅**
La cosa más pequeña que dice algo verdadero y accionable: *una ráfaga de IA dio forma a este archivo hace N días y no has vuelto desde entonces.* Lee un signal vivo y discriminante (el trailer), es honesto (recencia, no comprensión), y es el primer átomo literal del wedge. Difiere: el composite, la comprensión, la infra de análisis continuo, la definición formal multi-commit de "ráfaga".

**B. Naming: "Last contact" user-facing; "Pulso" = codename del arco. ✅**
Un timestamp prueba *contacto* y nada más. "Pulso/pulse" sobreclama un signal vivo de doble vía (el sistema afirmando que el humano sigue latiendo en el código) — se queda como nombre del arco, nunca en el archivo.

**C. v0.2 se compone del rastro de interacción del cuaderno. ✅**
La métrica-wedge de comprensión (v0.2) se construye de los **actos de testigo que el cuaderno YA captura** — `got it / didn't` markers, preguntas hechas sobre un archivo, confirmaciones de decisión — NO de git. Es el único substrato honesto de comprensión (Voronov). Lockeado como dirección.

## 3. Arquitectura lockeada (no re-discutir en los PRs)

1. **El trailer antes que la métrica.** Ninguna parte de Pulso lee `agent_line_ratio`/blame-author. Si un archivo no tiene commit con trailer, Pulso es **silencioso** sobre él (None, nunca 0). Ausencia ≠ cero (la cláusula anti-W4-3).
2. **La columna DB `cognitive_debt` ya es viva** (#151, `_persist_composite_scores`). Pulso es un campo nuevo, separado del heat.
3. **Trigger por commit, NO filesystem-watch** (Halberg). Watch hace thrash (lock global `analysis_lock`, SQLite sin WAL, tormentas de mtime por operaciones git, saves parciales). El commit-trigger está debounced por naturaleza. v0.1 ni siquiera necesita trigger nuevo — corre en el pase `copyclip analyze` existente.
4. **Cada número carga su distancia-de-testigo.** Renderiza exactamente hasta donde su rastro alcanza; calla (no cero) donde el rastro termina; se nombra a la distancia que realmente abarca. Implementado como: el campo es nullable, el surface confiesa su límite ("measures time, not understanding").
5. **El composite es un ledger, no un escalar** (v0.2). No se intenta un score-de-comprensión por archivo.

## 4. El plan en PRs (v0.1)

### PR-P1 — Ingest del trailer (la precondición) (~80 LOC)
- En `analyzer.py`, el pase de commits captura `Co-Authored-By` (vía `git log --pretty=...%(trailers:key=Co-authored-by)` o parse del body). Persiste `ai_attributed INTEGER` (0/1) en la fila `commits` (columna nueva + backfill en `db.py`).
- DoD: un test que ingesta commits con/sin trailer y asevera el boolean; commits viejos sin trailer → `ai_attributed=0`; `pytest -q` verde. NO toca el frontend ni la métrica todavía.

### PR-P2 — "Last contact" + limpieza del heat (~200 LOC)
- Nuevo `intelligence/pulso.py`: `build_last_contact(conn, project_id, path)`. Definición honesta:
  - `last_ai_burst` = commit AI-atribuido más reciente que tocó el archivo. Si no existe → **None** (silencioso).
  - `last_human_touch` = commit NO-AI-atribuido más reciente que tocó el archivo.
  - Relevante (no-silencioso) sii `last_ai_burst` existe y es ≥ `last_human_touch` (la última forma fue una ráfaga IA a la que el humano no ha vuelto). `last_contact_days = now − last_human_touch` (o desde el primer commit si nunca hubo toque humano).
  - Si el humano volvió después de la ráfaga (`last_human_touch > last_ai_burst`) → silencioso ("estás al día, nada que rastrear").
- Persiste `pulso_last_contact_days` (nullable) en `analysis_file_insights`, en el pase final junto a `_persist_composite_scores`.
- **Borra el factor muerto `agent_authored_ratio`** de `cognitive_debt.py` (0/203 vivo — el cadáver de W4-3) y quita su peso del denominador.
- **Recalibra `decision_gap`:** que se *desactive* (`signal_available=False`, deja el denominador) donde el área/proyecto tiene cero decisiones enlazadas, en vez de disparar a 100. La saturación uniforme es un hallazgo a nivel-proyecto, no deuda por-archivo (Serrano).
- DoD: tests de `build_last_contact` (ráfaga IA → toque humano = gap chico; ráfaga IA → nada = gap grande; sin ráfaga → None); el factor muerto fuera; `decision_gap` se desactiva sin decisiones; `pytest -q` verde; `copyclip bench` sin regresión.

### PR-P3 — Surface honesto de "Last contact" (~150 LOC)
- Una superficie mínima en el cuaderno que diga solo lo que prueba. Candidato: un tool del tutor `get_last_contact` (lista los archivos con ráfaga IA reciente a los que el humano no ha vuelto, citados) — conversational-native, igual que `get_heat`. El enriquecimiento del nodo `graph_view` es v0.2.
- Microcopy obligatorio (parte del deliverable, no pulido):
  - Label: **"Last contact"**.
  - Tooltip-confesión: *"AI changed this 9 days after you last touched it. This measures time, not understanding."*
  - Empty state: *"No AI burst recorded for this file since your last commit. Nothing to track here yet."* (ausencia como ausencia, no 0).
- DoD: una pregunta tipo "¿qué cambió la IA que no he revisado?" emite la lista citada; ausencia renderiza como ausencia; ningún string reclama comprensión/review/ownership.

## 5. Restricciones (off-limits)

- **Nunca leer `agent_line_ratio`/blame-author como signal de ráfaga.** Es el cadáver de W4-3 (0/203). Leer el trailer o renderizar silencio.
- **Nunca nombrar ni reclamar comprensión** desde git: ni "comprehension", "review", "owned", "in sync", "stale", "neglected", "pulse". El timestamp prueba contacto; un grado más es mentira (Wren).
- **Ausencia ≠ cero.** Sin ráfaga → None/silencio, nunca un número bajo tranquilizador.
- **No filesystem-watch.** Commit-trigger / pase existente.
- **No componer un score de comprensión por archivo** (es la forma equivocada; v0.2 es un ledger desde el rastro del cuaderno).

## 6. Diferido a v0.2+ (no es v0.1, guard de scope)

- **La métrica-wedge compuesta** desde el rastro del cuaderno (got-it markers, preguntas, ratificaciones de decisión) — el substrato de testigo (decisión C). Probablemente un arco propio.
- **El ledger ráfaga→gap→reconexión** (la forma correcta — Richter/Voronov), no un escalar.
- **Definición formal multi-commit de "ráfaga"** (v0.1 usa: un commit con trailer ES la ráfaga mínima).
- **Atribución por-línea** (v0.1 es commit-level vía blame SHA → trailer; per-line es upgrade de precisión).
- **Infra de análisis continuo** (commit-trigger real + WAL + `busy_timeout` + ledger durable que sobreviva el rewrite de `analysis_file_state`).
- **`test_evidence_gap`** (el siguiente binario que saturará — Richter) y **`review_staleness`** (mislabeled "human review"; lo subsume el "Last contact" honesto).

## 7. Riesgos

1. **El trailer es frágil sobre el workflow** (squash/rebase/amend dropean trailers; un commit IA sin trailer lee humano). Mitigación: tratar ausencia-de-trailer como *desconocido/humano* explícitamente; declarar la cobertura como límite (no reclamar certeza donde no hay trailer). Universalidad = claim de disciplina-de-commit, no garantía de runtime (Halberg/Richter).
2. **Re-sobreclamo invisible** (un número verde-plausible peor que el ~0 visible de W4-3). Mitigación: el silencio-en-ausencia + el tooltip-confesión + tests de procedencia.
3. **Whack-a-mole de factores binarios** (`test_evidence_gap` satura tras arreglar `decision_gap`). Mitigación: reconocido como problema de *forma* del score; v0.1 solo desactiva, v0.2+ replantea.
4. **Repo solo-dev** degenera signals de autor-switch/ownership. Mitigación: la ráfaga se ancla al trailer, nunca a identidad de autor.
