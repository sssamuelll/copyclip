# Wave 5 — Muerte del dashboard (kickoff)

**Fecha:** 2026-06-11
**Estado:** Ratificado por Samuel (2026-06-11). Las tres decisiones abiertas fueron resueltas por él.
**Precede:** nada — es la última ola de la absorción. Ejecuta ahora (la fecha innegociable era vie 19-jun; entra antes).
**Constitución:** `docs/superpowers/specs/2026-06-04-cuaderno-shell-consensus-design.md` §5-6 (§7 lista Wave 5).
**Plan que lo definió:** `docs/superpowers/plans/2026-06-11-wave-4-absorption.md` §7 L130.
**Fundación (mapeo del blast radius):** workflow `wave5-blast-radius`, 2026-06-11 (5 agentes read-only).

---

## 0. El marco

Wave 4 absorbió cada clase de pregunta del dashboard pre-rediseño en tools/widgets citables del cuaderno. Las páginas quedaron **huérfanas pero presentes**. Wave 5 las **borra físicamente** y colapsa la superficie a una sola: el cuaderno. No es scope creep — es el cierre prometido. La capacidad nunca se pierde: sobrevive en `anchor.py` (tools del tutor) + `mcp_server.py`, que leen la DB/git directo, no por los `/api/*`.

**Invariante de la ola:** se borra UI, nunca capacidad. Si un dato sale de un tool/MCP/endpoint que sobrevive, la página puede morir.

---

## 1. Survivors (lo que NO se toca)

- `CuadernoPage` — la superficie primaria (home full-screen).
- `Atlas3DPage` — codebase map (artifact renderer; se alcanza desde el cuaderno).
- `SettingsPage` — config + disparador de análisis (decisión E de Wave 4).
- `HandoffPage` — safe handoff.
- `utils/debt.ts` (+ `debt.test.ts`) — vivo vía el widget `GraphView` del cuaderno.
- `styles/atlas-chrome.css` (+ su test) — pasa a ser load-bearing: carga el chrome de los survivors.
- `api/cuaderno.ts`, `tool_catalog.py`, `anchor.py`, `mcp_server.py` (renombrado, no borrado), **todos los `/api/*`** (regla Cassian).

## 2. Decisiones ratificadas (Samuel, 2026-06-11)

**D1 — Navegación: cuaderno-only + menú en ⊞. ✅**
Muerto el Sidebar agrupado (cósmico), los 3 survivors se alcanzan con un menú/overlay pequeño que abre el ⊞ del cuaderno; cada survivor renderiza full-screen con "volver al cuaderno". El cuaderno es LA superficie; no hay nav persistente. Se borran `Sidebar.tsx` y las clases `.app/.sidebar/.nav-group/.main`.

**D2 — Rename MCP: + vocabulario `heat`. ✅**
No solo el mandato spec-literal (rename del server off `Oracle/Authority`). También alinear el vocabulario de la superficie MCP/handoff: `cognitive_debt`/"Fog of War" → `heat`, igual que el cuaderno (Wave 4). **Condición de honestidad:** se renombra la palabra SOLO repuntando el dato al motor vivo. Verificar primero si la columna `cognitive_debt` ya quedó viva tras PR #151 (`_persist_composite_scores`); si sí, el rename es seguro de una; si no, repuntar a `build_debt_breakdown` antes de renombrar. Nunca relabelar un cero muerto como `heat`.

**D3 — Backlog: cerrar el set supersedido. ✅**
CLOSE: Atlas #3,4,6,7,8,9,10,11,12 · Playground epic #86 + #87-96 · #15, #20 (superseded por la constitución) · #101 (sin fricción fechada). FREEZE #114 (settrace CPython-only; etiqueta, no cierre). Verificar-y-cerrar #105 (vitest existe; confirmar el test de `buildLaunchableRef`). KEEP: #21, #25, #84, #106, #146, #152; #138 abierto pero marcado post-Cruces. Marcar el spec de playground v1 como superseded.

## 3. El manifiesto de borrado (build-safe)

**Mueren (frontend):** 10 páginas — `Architecture`, `Changes`, `ContextBuilder`, `DebtNavigator`, `Decisions`, `ImpactSimulator`, `Planning`, `Reacquaintance`, `Risks`, `Timeline` — + `components/Sidebar.tsx` + `styles.css` + el shell-router de `App.tsx` + los métodos muertos de `api/client.ts`.

**Backend:** cero borrados de rutas. `/api/heatmap` y `/api/cognitive-load` leen la columna de deuda muerta (memoria de las dos máquinas) → candidatos a limpieza FUTURA, no Wave 5.

**Gotchas verificados (no son decisiones — trabajo obligatorio):**
1. **Borrar `styles.css` regresa HandoffPage.** Viven solo ahí: `.badge-high/-med/-low` (8 sitios en Handoff) + tokens `--accent-red`/`--accent-amber`; `--accent-cyan-soft` (Handoff:296); el `@import` de JetBrains/IBM Plex Mono (referenciado por atlas-chrome.css y cuaderno.css); el reset global (`box-sizing`/`body`/`focus-visible`) y los tokens base (`--bg`, `--text-tertiary`, `--accent`, `--accent-cyan`). → Migrar a `atlas-chrome.css` (o index.html para las fuentes) **antes** de borrar.
2. **El test "gate" miente.** `atlas-chrome.test.ts` pasa en verde pero solo chequea `.badge` base y tokens usados *dentro* del CSS — no los `.badge-high/-med/-low` ni los tokens que usan los `.tsx` (p.ej. `--accent-cyan-soft`). → Endurecerlo (RED) antes de migrar.
3. **`onOpenDashboard→setPage('reacquaintance')`** apunta a una página que muere → re-apuntar al menú ⊞ en el mismo commit; quitar el prop `onOpenDashboard` end-to-end si el flujo cambia.
4. **No borrar** `utils/debt.ts` (vive en `GraphView`).

## 4. El plan en PRs

### PR-W5-1 — Colapso a cuaderno-only + borrado del dashboard + muerte de `styles.css`
Un solo PR porque el shell (`.app/.sidebar/.nav-group`) vive solo en `styles.css`: colapsar y borrar van juntos.
1. **(TDD RED)** Endurecer `atlas-chrome.test.ts`: aseverar `.badge-high/-med/-low`; escanear los `.tsx` survivors (Handoff, Atlas3D, Settings, App) por `var(--token)` y exigir que cada token resuelva en `atlas-chrome.css ∪ cuaderno.css`.
2. **(GREEN)** Migrar a `atlas-chrome.css`: el `:root` faltante (`--bg`, `--text-tertiary`, `--accent`, `--accent-cyan`, `--accent-cyan-soft`, `--accent-amber`, `--accent-red`), el reset global, `.badge-high/-med/-low`; fuentes vía `<link>` en `index.html`.
3. **(TDD RED→GREEN)** Nueva navegación ⊞: test de que ⊞ abre el menú, elegir "map/handoff/settings" renderiza el survivor, "volver" regresa al cuaderno.
4. Reescribir `App.tsx`: cuaderno home + menú ⊞ + 3 rutas survivor full-screen + volver; quitar el shell-router, `loadAll()`, el estado de focus, el Sidebar, `PAGE_LABELS`. Re-apuntar/quitar `onOpenDashboard`.
5. Borrar las 10 páginas + `Sidebar.tsx` + `styles.css`; quitar el import en `main.tsx`; podar los métodos muertos de `client.ts` (mantener types).
- **DoD:** `npm run build` + `vitest` verde; el test endurecido verde; Playwright visual de los 3 survivors + el menú ⊞ sin regresión; cuaderno intacto.

### PR-W5-2 — Repuntar + renombrar MCP/handoff a `heat` (D2)
1. Verificar si la columna `cognitive_debt` ya es viva (post-#151). Repuntar `get_cognitive_load` + lecturas de deuda en `handoff.py` a `build_debt_breakdown` si hace falta.
2. **(TDD)** Renombrar el server off `Oracle/Authority` (`mcp_server.py:25` id, `:23` comentario, `cli.py:313` help, `cli.py:316` banner, `mcp_server.py:338` string "Dashboard"). Renombrar vocabulario `cognitive_debt`/"Fog of War" → `heat` en `get_cognitive_load` (nombre/desc/output) y en los payloads de `handoff.py`. Actualizar + renombrar `test_mcp_intent_oracle.py`.
- **DoD:** `pytest -q` verde; ningún string `Oracle`/`Authority`/`cognitive debt`/`Fog of War` cruza al agente externo; el número bajo `heat` es el motor vivo, no la columna muerta.

### PR-W5-3 — Roadmap ≤3 + README + spec de playground superseded (docs)
1. Reescribir `src/copyclip/roadmap.md` a ≤3 ítems: (1) Cruces/Junctions v0.1 (#146), (2) Pulso (#152), (3) Intent Drift Surface. Cortar el resto (interactive artifacts, kanban bi-direccional, audit webhooks, 3D layers, VSCode ext, multi-repo, exportable constraints).
2. Re-enmarcar README: los headings "Cognitive Debt Navigator" y "Codebase Map" describen páginas que mueren/se demotan a alcanzables-desde-el-cuaderno. Tono cuaderno; verificar el blurb de roadmap (README:161-163).
3. Flip del status del spec `2026-05-22-anchored-playground-design.md:4` → superseded por la constitución 2026-06-04.
- **DoD:** README y roadmap no nombran superficies muertas; sin drift de vocabulario (cf. PR #85).

### Acción externa — Purga de backlog (D3)
`gh issue close` con comentario para el set supersedido; etiqueta freeze en #114; verificar-y-cerrar #105. NO es un PR; requiere el OK ya dado.

## 5. Restricciones (off-limits)

- **No borrar rutas backend.** La capacidad sobrevive vía `anchor.py`/MCP; los endpoints se quedan (Cassian).
- **No borrar** `utils/debt.ts`, `atlas-chrome.css`, ni su test.
- **No relabelar deuda muerta como `heat`** — repuntar al motor vivo primero (D2).
- **No reescribir los docs históricos** (`plans/`, specs viejos): son registros con fecha, correctos para su día. Solo docs VIVOS (README, roadmap) + el string MCP visible al agente.
- **No tocar la cuarentena** (`/api/issues`, `/api/analyze/*`).
- **No añadir widget kinds nuevos.**

## 6. Riesgos

1. **Regresión visual de HandoffPage** por el `styles.css` muerto → mitigado por el test endurecido + migración previa (gotcha 1-2).
2. **`onOpenDashboard` colgante** → editar en el mismo commit que borra Reacquaintance (gotcha 3).
3. **Rename MCP que relabela un cero** → condición de honestidad de D2 (repuntar antes de renombrar).
4. **Cierre prematuro de #105** → verificar el test de `buildLaunchableRef` antes de cerrar.
5. **Drift de vocabulario README/roadmap** → anclar el reescrito a los 3 survivors + cuaderno (cf. PR #85).
