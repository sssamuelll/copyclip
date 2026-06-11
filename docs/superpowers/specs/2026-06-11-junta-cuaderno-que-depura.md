# Junta del roster — El cuaderno que depura

**Fecha:** 2026-06-11 (jueves)
**Estado:** Propuesto — pendiente de ratificación por Samuel
**Convocatoria (verbatim):** *"quiero lograr que copyclip sea una herramienta que ayude a los desarrolladores a entender su codigo, para esto debe ser una herramienta de debugging de alto nivel, interactiva, de aprendizaje, todo desde la simpleza de un cuaderno. hasta ahora vamos por buen camino pero aun no termina de ser lo que se quiere."*
**Provenance:** Kenji (mapa del pipeline) + explorador (inventario de fricciones) → consejo de 10 voces en paralelo (Voronov, Richter, Halberg, Serrano, Vale, Lyra, Cassian, Tane, Rune, Wren) → Axiom-0 (cierre). 13 agentes, deliberación 2026-06-11.

---

## 1. El veredicto central (Axiom-0, unánime en sustancia)

> **El cuaderno solo puede enseñar lo que puede demostrar.**
> Invariante: *nada cruza hacia el humano que el sistema no haya computado o confesado.*

Las tres palabras de la convocatoria **no piden una constitución nueva**. Son el invariante ya ratificado (cláusula 4 + ontología de artefactos, spec 2026-06-04) observado desde tres dimensiones:

| Palabra | Lectura constitucional | Casa |
|---|---|---|
| "debugging de alto nivel" | El invariante aplicado al **runtime**: la rama existe solo si la celda la computa | Wedge diferido del #139 (rama como objeto de primera clase) |
| "interactiva" | El invariante aplicado al **gesto**: el humano interroga, el sistema demuestra. "Exposición, no autoría" no la limita: la define | #138 (graph click-to-drill) + inputs vivos ya embarcados (#141) |
| "de aprendizaje" | El invariante aplicado al **tiempo**: lo aprendido es evidencia de comprensión recuperada — **o no entra** | Sin mandato hasta tener definición operativa + fricción fechada (freno, test 2) |

La insatisfacción ("aún no termina de ser lo que se quiere") es la percepción exacta de los puntos donde **narración sustituye a computación** — el sistema todavía muestra cosas que no demuestra. El orden del plan no se decide: lo genera el invariante — *la membrana se sella de afuera (lo que ya toca el ojo) hacia adentro (lo que cruzará después)*.

Una deriva detectada y corregida sin debate: el plural "los desarrolladores" contradice la cláusula 5 (herramienta personal). La evidencia de dolor existe en singular.

## 2. La deuda de honestidad (sellar ANTES de profundizar)

Verificada en HEAD por cuatro voces independientes:

1. **`suggested_inputs` cruza al iframe sin gate** (widget_checks.py:63-73 no lo toca; se vuelve dropdown ejecutable en playground.py:476-491). El currículo pedagógico del playground es narración del modelo horneada en UI viva. Es la deuda "illustrative disclosure" de Wave 2, aún impaga.
2. **`verdict.source == "floor"` se renderiza como answer juzgada** sin nota de procedencia (FrameDynamic.tsx:44-46 solo distingue `unjudged`). El sistema se pronuncia sobre sí mismo y firma como juez.
3. **call_expr de métodos detona por construcción**: `Parent(...)` ejecuta el constructor con `Ellipsis` (playground.py:449-458). Bloqueante para cualquier tracing encima (Halberg).
4. **Ejecución al cargar sin consentimiento**: el floor construye sin inputs → `mo.ui.text(value="")` → la función real corre con `""` al boot del iframe, sin sandbox, con side effects posibles (compositor.py:156-164, playground.py:492). Falta política de efectos.
5. **Trío de widgets sin gate**: graph_subset / sequence_diagram / callers_tree retornan `None` en widget_checks.py:87 — el único camino de emisión que cruza al usuario sin verificación de evidencia. **Gate o guillotina** (decisión abierta §6).
6. **El veredicto del juez no tiene jerarquía visual**: usa la misma `.callout` que el contenido del modelo, y la procedencia se imprime en 11px `--ink-4` (~2.2:1) — la línea más honesta del producto es la más tenue de la página (Tane). La regla ratificada "un artifact nunca más autoritativo que su fundamento" se viola en el énfasis.
7. **Copy que miente**: "en pausa: hay otro ejemplo corriendo" (strings.ts:74) promete reanudación que no existe — el proceso muere y el relaunch parte de cero.

## 3. El calendario (Cassian, ajustado por el consejo)

**Viernes 2026-06-12 — SHIP #139**
- 09:00–12:00: tarea 2.6 (smoke manual: widget-no-prosa, input editable, cruce de línea 162) + buffer de fix.
- 12:00–13:00: merge a main vía PR, cerrar épico #139. Abrir issue "arco Cruces v0.1" con SOLO el primer ítem del wedge.
- Tarde: **escribir el kickoff de Wave 4** (sin ese plan, el 19-jun cae — riesgo #1 identificado) + issue-checklist único del sweep DELETE de Wave 5.

**Lunes 2026-06-15 — verdad antes que capacidad (~1 día)**
- Fixes de honestidad (§2): disclosure de suggested_inputs (texto exacto de Wren abajo), badge de procedencia `floor`, copy "en pausa", registro visual propio para veredicto/procedencia del juez (corte 1 de Tane).
- PR "entierro" (Rune, ≈ −400 líneas): StubMarimoRunner + cadena ImportError (playground.py:589-602, server.py:96-112), `PLAYGROUND_SOURCES` → `{'cuaderno'}` + modo `edit` sin llamador, 6 métodos huérfanos de client.ts, 6-7 rutas backend sin cliente, `compose_frame`, tests del stub y de `source="atlas"`, 14 docs pre-pivote (KEEP: REJECTED.md, contratos MCP/Wave-4, LOCAL_DEVELOPMENT, LANGUAGE_SUPPORT).

**Mar 16 – Mié 17 — Wave 4 (absorción por clase de pregunta)**
- PR1: risks → callouts citados. PR2: impact/context-builder → tools del tutor. PR3: clúster temporal-causal (reacquaintance/timeline/decisions/changes → git_* tools) + reconciliación de chrome. Tematizar el interior de marimo (paper/ink/sienna) o declarar la deuda.

**Jue 18 – Vie 19 — Wave 5 (muerte del dashboard, EN FECHA)**
- Regla ratificada por el consejo: **la página que no esté absorbida el 18, muere el 19 igual.** Borrar en fecha > absorber tarde.
- Sweep ampliado (Rune): no solo router/Sidebar — las rutas de server.py servidas solo por páginas muertas mueren con ellas (~−900 líneas). CONSIDER: verificar `/api/analyze/*` (wizard onboarding) antes de tocar.
- Purga de backlog (~20 cierres en una mañana, Lyra): Atlas #3-#12 (superseded), conectores #87-#96 (#87-#89 done-elsewhere, resto muertos), #15, #20 (superseded por la constitución), #101 (sin fricción fechada). #114 congelado post-wedge. #21/#25/#84/#105/#106 = higiene sin semana propia.
- Rename MCP, sweep README/roadmap (≤3 ítems), registrar spec playground-v1 como superseded.

**Semana del 22-jun — arco "Cruces" v0.1 (debugging de alto nivel, primera entrega)**
> Core embarcable en una frase: *el widget de playground muestra, junto al resultado, **qué rama ejecutó el input que tú editaste** — un valor computado, nunca narrado, en el slot único y los 480px actuales.*
- Orden de Halberg (1→4→2→3): (1) fix call_expr de métodos + política de efectos (la celda no ejecuta al cargar sin input confirmado, o gate de pureza del analyzer); (4) gate de suggested_inputs alimentando ejecución observada; (2) traza de rama vía `sys.settrace` scoped a la llamada — líneas ejecutadas renderizadas como valor computado en celda + snapshot de locals en return (repr truncado); (3) **contraste de dos inputs DENTRO de un solo notebook** — dos `mo.ui`, celda de diff computada; un subprocess, jamás dos iframes.
- **Ship: viernes 2026-06-26.**

**Después (en orden):** #138 reducido a click-to-drill que dispara pregunta al tutor (lo único asimétrico del issue; motion/peso/labels = pulido con techo) → evidencia conductual (ledger de ejecución análogo al ReadLedger; `got_it` como input del compositor — hoy es memoria de solo escritura, persistence.py:97-105 sin un solo consumidor). Esa es la única forma constitucional de "aprendizaje" sobre la mesa, y entra solo con fricción fechada.

## 4. Lo que NO se construye (permission slip, Cassian)

Multi-slot / segundo subprocess lado a lado (el cap 5 del backend espera) · escape del 480px · drag/física/motion del grafo · learning paths, drills, detección de misconceptions, modelo del usuario · inspector de variables / breakpoints / DAP embebido · time-travel tracing · kernels persistentes · persistencia del playground · #114 multi-lenguaje (settrace es CPython-only; la universalidad colapsa ahí) · celdas editables (techo ratificado) · pedagogía adaptativa (segunda fuente de verdad fuera de la jurisdicción del juez).

## 5. Lenguaje (Wren)

- **La claim se defiende, no evoluciona**: las tres palabras son medios; la claim nombra el fin. Subtítulo opcional: *"Un cuaderno que depura tu comprensión, no tu código."*
- Arco nombrado **"Cruces / Junctions"** solo en plan e issues; en pantalla, únicamente etiquetas computadas ("este input tomó la rama de la línea N"). "Forks/branches" cortados por colisión con git.
- Al absorberse Reacquaintance como tool: renombrar a **reentry / regreso**.
- Widget kinds en pantalla como caption editorial ("mapa", "quién llama", "secuencia"), nunca el nombre de schema; cortar la palabra "widget" de la cabecera (Tane).
- Disclosure exacta: *"los inputs son ejemplos del tutor, no valores leídos de tu código. la función que llaman es real."* / Evicción: *"se cerró para dar lugar a otro ejemplo. vuelve a ejecutar para empezar de cero."*

## 6. Decisiones abiertas — solo Samuel

1. **"Aprendizaje"**: ¿puedes nombrar fecha y momento en que el cuaderno te explicó algo y tú no lo aprendiste — o la palabra entró por la audiencia hipotética que tu propio freno prohíbe? (pregunta incómoda de Lyra). Sin fricción fechada, queda fuera del plan.
2. **Trío sin gate** (graph_subset / sequence_diagram / callers_tree): ¿gate (trabajo en Wave 4) o guillotina (corte ya)? Regla de Richter mientras tanto: cero widgets nuevos hasta que widget_checks cubra los tres.
3. **El CLI original** (clipboard.py, minimizer.py, presets.py — pre-inteligencia): nadie ha declarado si vive o muere. Que alguien lo declare.
4. **Ratificación del calendario** §3, en particular la regla "la página que no esté absorbida el 18, muere el 19".

## 7. Riesgo principal

Deslizar el 19-jun. Una fecha ratificada que cae convierte la constitución entera de ley en sugerencia (Lyra, Cassian, Axiom-0: *"una fecha deslizada es narración"*). La ambición nueva no pone la fecha en riesgo — la ausencia del plan de Wave 4 sí; por eso ese kickoff se escribe mañana por la tarde.
