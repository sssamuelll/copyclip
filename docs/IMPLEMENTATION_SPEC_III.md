# Implementation Spec: Intent Intelligence (III) - V1.0

**Misión:** Cerrar la brecha entre la infraestructura de datos actual y la visión de "Conexión Cognitiva". El sistema debe pasar de un análisis pasivo a una protección activa de la intención humana.

---

## 🛠 Módulo 1: Handoff Consciente (Intent-Aware Bundling)
**Contexto:** Actualmente, `copyclip` envía código pero no las reglas. El agente receptor entra "ciego".

### Tareas:
- [ ] Modificar `src/copyclip/intelligence/db.py`: Asegurar que `get_active_decisions` sea robusto y accesible desde el CLI principal.
- [ ] Modificar `src/copyclip/__main__.py` (o el orquestador del output):
    - Al generar el bundle final, llamar a `get_active_decisions(folder)`.
    - Prependear al output un bloque Markdown:
      ```markdown
      ## 🎯 ACTIVE ARCHITECTURAL INTENT & DECISIONS
      > Human-defined constraints for this project.
      
      - [ID] Title: Summary
      ...
      ```
- [ ] **Validación:** Ejecutar `copyclip . --print` y verificar que las decisiones "Accepted" aparezcan al inicio.

---

## 🛠 Módulo 2: Cognitive Load & "Fog of War"
**Contexto:** El desarrollador se desconecta cuando no sabe qué partes del código son suyas y cuáles del agente.

### Tareas:
- [ ] Modificar `src/copyclip/intelligence/analyzer.py`:
    - Definir una lista de `AGENT_SIGNATURES = ["cursor", "windsurf", "agent", "github-actions", "bot"]`.
    - En la fase de `PHASE_GIT_HISTORY`, usar `git blame` o analizar el `author` de los commits para cada archivo.
    - Calcular el ratio: `Agent_Lines / Total_Lines`.
    - Guardar en la tabla `analysis_file_insights` la columna `cognitive_debt` (0-100).
    - `Score = (Ratio_Agente * 100) * (Factor_Tiempo_Sin_Review)`.
- [ ] **Validación:** El `summary_json` de los snapshots debe incluir ahora un `average_cognitive_debt`.

---

## 🛠 Módulo 3: Auditoría Semántica de Deriva (Drift Auditor)
**Contexto:** La comparación actual de deriva es léxica (palabras). Necesitamos que sea lógica.

### Tareas:
- [ ] Crear el comando `copyclip audit` en `src/copyclip/intelligence/cli.py`.
- [ ] Lógica del Auditor:
    - Identificar archivos con `intent_drift` (basado en la vinculación de `decision_links`).
    - Para cada archivo sospechoso, enviar al LLM: `Decision_Text` + `Code_Diff`.
    - Prompt: *"¿Este cambio contradice la intención de la decisión? Responde Score (0-100) + Razón."*
    - Actualizar el registro en la tabla `risks` con `kind='semantic_drift'`.
- [ ] **Validación:** El comando `audit` debe imprimir un reporte de "Violaciones de Intención" detectadas por IA.

---

## 🛠 Módulo 4: UI de Alineación de Intención (Visual)
**Contexto:** El humano procesa mejor la información visualmente.

### Tareas:
- [ ] Modificar `frontend/src/pages/ArchitecturePage.tsx`:
    - Añadir un toggle para colorear los nodos según `cognitive_debt` (Verde: Humano, Rojo: Agente).
- [ ] Modificar `frontend/src/pages/NarrativePage.tsx`:
    - Cambiar el prompt de generación de historia para que compare el snapshot actual con el anterior.
    - Enfoque: *"Explica qué cambió en la intención, no solo en los archivos."*
- [ ] **Validación:** Ver el mapa de calor de "Fog of War" en el dashboard.

---

## 📝 Notas para el Agente:
1.  No rompas la compatibilidad con el esquema de DB actual, solo añade columnas si es estrictamente necesario (ya están casi todas).
2.  Prioriza el **Módulo 1**, ya que es el que tiene mayor impacto inmediato en la calidad de las respuestas de otros agentes.
3.  Usa el `LLMClientFactory` existente para todas las llamadas a IA.
