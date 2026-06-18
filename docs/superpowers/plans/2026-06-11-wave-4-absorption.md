# Wave 4 — Absorción por clase de pregunta (kickoff)

**Fecha:** 2026-06-11
**Estado:** Propuesto — pendiente de ratificación por Samuel (las decisiones de §3 son suyas)
**Ejecuta:** lun 15 – mié 17 jun. **Precede a Wave 5** (muerte del dashboard, vie 19 jun, innegociable).
**Constitución:** `docs/superpowers/specs/2026-06-04-cuaderno-shell-consensus-design.md` §5-6
**Plan de la junta:** `docs/superpowers/specs/2026-06-11-junta-cuaderno-que-depura.md`
**Fundación (mapeo del estado real):** workflow `wave4-fundacion`, 2026-06-11.

---

## 0. El marco: ráfagas conectadas

Samuel (2026-06-11): *"el desarrollo de software se lleva por ráfagas; es importante mantener las ráfagas conectadas; el único que puede conectarlas es el humano; allí está la magia de copyclip — un instrumento capaz de mantener al usuario en su intención y que perdure en las ráfagas de desarrollo."*

Esto afila el wedge temporal-causal: comprensión no es solo "recuperar decisiones que no tomaste", es **mantener la intención del humano intacta y conectada a través de ráfagas discontinuas de desarrollo asistido por IA**. La ráfaga es rápida; el hueco entre ráfagas es donde se fuga la propiedad. CopyClip sobrevive el hueco y reconecta al humano con su propia intención.

Dos decisiones de §3 (E y G) crecieron por este marco: el **análisis debe seguir el ritmo de las ráfagas** (instantáneo, en background, sin paso bloqueante), y la **historia/detección de cambios es el tejido conectivo** del sistema (no pulido, sino infraestructura del propio CopyClip para coser una ráfaga con la siguiente).

---

## 1. El hallazgo que cambia el plan

La constitución dice: *"el clúster temporal-causal (reacquaintance/timeline/decisions/changes) colapsa a tools **git_\* existentes**"*. El mapeo prueba que **eso es solo parcialmente cierto**, y la diferencia es load-bearing por el invariante de la junta (*"nada cruza al humano sin ser computado o confesado"*):

| Pregunta | ¿Cubierta por tools de hoy? | Evidencia |
|---|---|---|
| "¿qué cambió / cuándo / quién?" (changes, timeline-commits) | **Sí** — `git_log`, `git_diff`, `git_blame` | `anchor.py:190-261` |
| "¿qué decisiones se tomaron?" (decisions, planning) | **No** — no hay tool sobre la tabla `decisions` | `tool_catalog.py:11-171` (ausencia) |
| "¿qué debo re-leer al volver?" (reacquaintance) | **No** — el motor con scoring propio no se expone | `reacquaintance.py:147-489` |
| "¿qué se rompe si toco esto?" (impact) | **No** — la BFS vive en el endpoint, no como tool | `server.py:700-743` |
| "¿qué decisiones tocaron este archivo?" (archaeology) | **No** — correlación commit↔`decision_refs` sin tool | `server.py:764-849` |

**Consecuencia lockeada:** absorber estas páginas pidiéndole al modelo que reconstruya el scoring de reacquaintance, o que adivine qué decisiones existen, **es fabricación** — la cláusula 4 muriendo donde más convence. Por tanto **Wave 4 crea los tools faltantes ANTES de borrar las páginas.** El tool nace; la página muere después. No al revés.

Esto es trabajo adicional al que la constitución suponía. Es la corrección honesta del alcance, no scope creep: el alcance siempre fue "absorber sin fabricar"; el mapeo solo reveló el costo real.

## 2. Decisiones arquitectónicas YA lockeadas (no las re-discutas en los PRs)

Derivadas del invariante + la constitución + el mapeo. Vinculantes para todos los PRs de abajo.

1. **Tool antes que borrado.** Ninguna página del clúster se borra hasta que su tool/artifact lo reemplace y pase el gate de honestidad. (El borrado físico del router/Sidebar es **Wave 5**, no Wave 4 — Wave 4 deja las páginas huérfanas pero presentes.)
2. **Toda respuesta absorbida es un block citado o un valor de tool, nunca narración.** Un callout de riesgo sin la cita de su fila en la tabla `risks` no se emite.
3. **Cuarentena (no borrar):** `/api/issues`, `/api/analyze/*`. Motores que sobreviven vía MCP o tool: reacquaintance, debt, handoff. (`server.py:1243-1274`, `1330-1808`, `mcp_server.py:28-131`).
4. **Un solo renderer por artifact.** Architecture monta sobre el `graph_view` widget de Wave 3 (`GraphView.tsx`, ya en `cuaderno.css`); el grid de divs de `ArchitecturePage` muere. Cero segundo renderer.
5. **El "fabricated ≥6 severity" del Impact muere** — vive solo en `ImpactSimulatorPage.tsx:33` (frontend). El motor BFS del backend es citable y se conserva tal cual.
6. **Los tools nuevos son del cuaderno** (`anchor.py` + `tool_catalog.py`), no MCP. MCP es la superficie de agentes externos; el tutor tiene la suya. (No confundir: los `git_*` del tutor ya viven en `anchor.py`, no en `mcp_server.py`.)
7. **El borrado de chrome (nebula `styles.css`, Sidebar, router) es Wave 5.** Wave 4 solo reconcilia: mueve a `cuaderno.css` lo que sobrevive necesita (ver §3.D).

## 3. Decisiones ratificadas (Samuel, 2026-06-11)

**A. Crear los ~5 tools nuevos. ✅ RATIFICADO.**
Es lo único que respeta el invariante. Recortar haría que el tutor fabrique el scoring de reacquaintance → viola cláusula 4. Costo asumido: ~3-4 días de trabajo de tools.

**B. Conservar las mutaciones de decisiones. ✅ CAMBIADO (default era solo-lectura).**
El tutor obtiene un **write-tool** para transicionar estado de decisión (anchor/integrate/transcend, sobre `PATCH /api/decisions/{id}`). Es la única excepción al techo "exposición, no autoría": cambiar el estado de una decisión es un acto del humano sobre su propio ledger, no autoría de código. El write-tool exige confirmación explícita y registra en `decision_history`. Va en PR-W4-2.

**C. Heredar la capa de fog en el artifact de Architecture. ✅ CAMBIADO (default era sin fog).**
`get_module_graph` se enriquece con `cognitive_debt_score` de `analysis_file_insights`; el `graph_view` colorea los nodos por deuda (fog), como hace hoy `ArchitecturePage`. Trabajo extra en PR-W4-3. El coloreado es cyan-only/neutral (deuda = dato neutro, no alerta — [[feedback-cyan-only-contextual]]).

**D. Migrar `.atlas-*` a `cuaderno.css`. ✅ RATIFICADO (default).**
En PR-W4-4, para que Wave 5 pueda borrar `styles.css` sin romper Atlas3D.

**E. Análisis instantáneo, en background, con avisos en frontend Y CLI. ✅ AMPLIADO (default era "migrar el botón a Settings").**
Esto es más grande que migrar un disparador: el análisis debe **seguir el ritmo de las ráfagas** (§0) — instantáneo (incremental, apoyado en `analysis_file_state`), continuo en background, sin paso bloqueante, con avisos no-intrusivos en ambas superficies. Se parte en dos:
- **Mínimo en Wave 4 (PR-W4-4):** el análisis corre en background disparado sin depender de `DebtNavigatorPage` (que muere), con un aviso de progreso/completitud en frontend + un aviso en CLI. Lo justo para que la página muera sin perder el arranque.
- **Arco propio "análisis continuo" (post-Wave-5, issue aparte):** instantáneo/incremental siempre, watch del filesystem o trigger por commit, avisos ricos. Es infraestructura del wedge de ráfagas, no parte de la absorción — merece su propio kickoff. *(Naming pendiente — candidato "Pulso".)*

**F. HandoffPage intacta hasta Wave 5. ✅ RATIFICADO (default).**

**G. `get_story_snapshots` como tool de ALTO retorno. ✅ CAMBIADO (default era colapsar a git_log).**
La historia/detección de cambios es el **tejido conectivo entre ráfagas** (§0), de alto valor para el propio sistema, no solo para el usuario. `get_story_snapshots` es tool de primera clase en PR-W4-1, y alimenta tanto la timeline absorbida como el arco de análisis continuo (E). No se colapsa a `git_log`; el narrative-shift layer se preserva.

## 4. El plan en PRs

Orden por dependencia: **tools → absorción → artifact → chrome.** Cada PR es delegable a un dev agent con el formato de kickoff (identidad, contexto, decisión lockeada, pasos, DoD, restricciones).

### PR-W4-1 — Tools del tutor: el clúster que falta (~350 LOC)
La columna vertebral. Sin esto, todo lo demás fabrica.
- En `anchor.py` + registro en `tool_catalog.py`, crear (cada uno devuelve datos citables, no scores inventados):
  - `get_decisions(status?, limit?)` → lee `decisions` (+ `decision_history`, `decision_links`). Para decisions + planning.
  - `get_reacquaintance_briefing(mode, window, checkpoint)` → wrappea `build_reacquaintance_briefing` (`reacquaintance.py:147`). Decisión A2: ¿payload completo o `top_changes`+`read_first`? *Default: recortar a `top_changes`+`read_first`+`relevant_decisions` para no reventar el context window.*
  - `get_reverse_dependents(path)` → porta la BFS de `server.py:713-743`. Para impact.
  - `git_archaeology(file)` → `git log -- file` + JOIN `decision_refs`. Para changes/archaeology.
  - `get_story_snapshots(range?)` → lee `story_snapshots` (decisión G, alto retorno). Para el narrative-shift de la timeline y, más adelante, el arco de análisis continuo. Si el análisis no corrió, degrada explícito a `git_log` (no inventa).
- DoD: cada tool aparece en `build_tool_definitions()`; un test por tool que verifica shape + que los datos provienen de la DB/git (no del modelo); `pytest -q` verde.
- Diff: ~420 LOC + tests. **NO** toca frontend. **NO** borra ninguna página.

### PR-W4-2 — Risks + Planning/Decisions como blocks citados (~200 LOC)
- Risks: el tutor responde preguntas de riesgo con `callout` blocks, **citación obligatoria** a la fila de `risks` (`{area, kind, rationale, score}` de `analyzer.py:864-985`). Decisión abierta del mapeo: *forzar `citations` no vacías en callouts que afirmen riesgo/decisión* — lockeado a SÍ (es el invariante; el gate de callout hoy no lo exige, `quality.py:181-226`, así que se añade la regla).
- Planning/Decisions: el tutor lee el ledger vía `get_decisions` (de PR-1) y lo presenta como blocks.
- **Write-tool de mutación de decisiones (decisión B):** `set_decision_status(id, status)` sobre `PATCH /api/decisions/{id}`, con confirmación explícita del humano y registro en `decision_history`. Única escritura permitida en Wave 4; es acto del humano sobre su ledger, no autoría de código.
- DoD: una pregunta de riesgo emite callout con cita verificable; una pregunta de "estado de decisiones" lista el ledger citado; transicionar una decisión vía cuaderno escribe `decision_history` y exige confirmación; bench no regresiona.
- Diff: ~280 LOC + tests.

### PR-W4-3 — Architecture como artifact sobre graph_view, con fog (~200 LOC)
- El tutor responde preguntas de estructura llamando `get_module_graph` y emitiendo un `graph_view` (el bridge ya existe, `widget_checks.py:18-59`).
- **Fog (decisión C):** `get_module_graph` se enriquece con `cognitive_debt_score` de `analysis_file_insights`; el `graph_view` colorea nodos por deuda. Coloreado cyan-only/neutral. El gate de honestidad sigue exigiendo que cada nodo/arista venga de la evidencia del turno.
- DoD: una pregunta de arquitectura emite `graph_view` con fog que pasa el gate; `ArchitecturePage` queda huérfana (sin borrar aún).
- Diff: ~200 LOC. Sin segundo renderer.

### PR-W4-4 — Chrome + análisis en background (~280 LOC)
- Migrar a `cuaderno.css` lo que sobrevive y hoy depende de `styles.css`: `.atlas-*` (decisión D), `.badge`/`.badge-high`, `.fog-*` si algún superviviente las usa.
- **Análisis en background con avisos (decisión E, mínimo de Wave 4):** el arranque del análisis deja de depender de `DebtNavigatorPage`; corre en background no-bloqueante (job ya existe, `/api/analyze/*` en cuarentena), con un aviso de progreso/completitud en el frontend (no-intrusivo, tono cuaderno) **y** un aviso en CLI. Lo justo para que la página muera sin perder el arranque. La versión instantánea/incremental/continua es el arco propio (ver §7).
- DoD: Atlas3D y Settings renderizan sin `styles.css` cargado (prueba quitándolo temporalmente); disparar análisis no bloquea y notifica en ambas superficies; `styles.css` queda listo para que Wave 5 lo borre.
- Diff: ~280 LOC.

### PR-W4-5 — Context Builder como tool (~180 LOC) *(opcional en Wave 4; puede ir a Wave 5)*
- `assemble_context` tool sobre `/api/issues` + `/api/assemble-context` (`server.py:1913-2056`). El más complejo; ambos endpoints en cuarentena ya.
- *Default: si no cabe antes del 18, la página muere el 19 igual (regla de Cassian) y este tool sale post-Wave-5* — `/api/issues` y `/api/assemble-context` sobreviven, así que no se pierde capacidad, solo la UI.

## 5. Restricciones (off-limits)

- **No borrar el router, Sidebar, ni `styles.css`** — eso es Wave 5. Wave 4 deja páginas huérfanas, no las elimina.
- **No fabricar.** Si un dato no sale de un tool/git/ledger citable, no se emite. Aplica especialmente a reacquaintance scoring y risk scores.
- **No tocar la cuarentena** (`/api/issues`, `/api/analyze/*`).
- **No reindent masivo.** Helpers > wraps literales (aprendizaje previo).
- **No añadir widget kinds nuevos.** Los 5 existentes + `callout` block bastan. (Y los tres sin gate —graph_subset/sequence_diagram/callers_tree— no se usan para Wave 4; su gate-or-guillotine es decisión aparte de la junta.)

## 6. Definition of done (Wave 4 completa)

- [ ] Los ~5 tools nuevos existen, registrados, con tests que prueban procedencia de datos (no del modelo).
- [ ] Cada clase de pregunta (changes, timeline, decisions, reacquaintance, risks, impact, architecture) tiene una respuesta del tutor citada/verificable — demostrada con una pregunta real en el cuaderno vivo.
- [ ] `Atlas3DPage` y `SettingsPage` sobreviven sin `styles.css`.
- [ ] `pytest -q` verde; `copyclip bench` sin regresión (regenerar `corpus_sha` solo si es intencional y revisado).
- [ ] Las 7 páginas absorbidas quedan huérfanas pero presentes; ninguna se borró (eso es Wave 5).

## 7. Lo que NO es Wave 4 (guard de scope creep)

Borrado físico del router/Sidebar/14 páginas/`styles.css` (Wave 5) · rename MCP (Wave 5) · roadmap ≤3 ítems (Wave 5) · el arco "Cruces" #146 (post-Wave-5) · #138 graph interactivo (post-Cruces).

**Arco propio (no Wave 4, derivado de decisión E):** *análisis continuo* — instantáneo/incremental siempre, watch de filesystem o trigger por commit, avisos ricos que siguen el ritmo de las ráfagas (§0). Es infraestructura del wedge de ráfagas; merece su propio kickoff. Candidato de nombre: "Pulso". Wave 4 solo entrega el mínimo de background+avisos (PR-W4-4).

## 8. Riesgos

1. **El alcance de tools (§1) no cabe en 3 días.** Mitigación: PR-W4-1 es la prioridad absoluta; si algo se cae, cae PR-5 (context builder), no los tools del clúster. Regla de Cassian: la página muere el 19 aunque su tool no esté perfecto, mientras el endpoint sobreviva.
2. **Fabricación silenciosa en la absorción.** Mitigación: la regla "citación obligatoria en callouts de riesgo/decisión" + tests de procedencia en los tools.
3. **Atlas roto por la muerte de nebula.** Mitigación: PR-W4-4 migra `.atlas-*` antes de que Wave 5 borre `styles.css` (decisión D).
4. **Deslizar el 19-jun.** Mitigación: Wave 4 no bloquea Wave 5 — las páginas se borran el 19 estén o no absorbidas; lo que importa es que el endpoint/tool sobreviva para no perder capacidad.
