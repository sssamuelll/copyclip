# Spec: Cognitive Connection & Intent Alignment (CCIA)

## 1. The Problem: "The Intent Drift"
In the era of AI-agentic development, code volume is exploding while human understanding is shrinking. 
- **The Disconnection:** Developers approve changes they haven't fully internalized because the context window of the change exceeds their immediate cognitive capacity.
- **The Drift:** Agents make micro-decisions that seem correct in isolation but gradually steer the project away from the original human intent.
- **The Result:** A codebase that "works" but is no longer "owned" or "understood" by its creator.

## 2. The Vision
CopyClip must evolve from a "Context Compiler" into an **Intent Anchor**. 
> **Goal:** Enable the developer to maintain a 100% mental map of the project with <5% of the traditional cognitive effort.

## 3. Core Pillars (The CCIA Framework)

### A. Intent Anchoring (Active Decisions)
- **Concept:** Every major architectural path must be anchored to a "Human Decision".
- **Implementation:** Link `copyclip decision` entries to specific AST nodes or file patterns.
- **Validation:** The `analyzer.py` should flag code changes that contradict existing decisions (e.g., "Agent introduced a Singleton, but Decision #12 says 'No Singletons'").

### B. Cognitive Load Scoring (The "Fog of War" Metric)
- **Concept:** Quantify how much of the project is "dark" to the developer.
- **Metric:** `CognitiveDebt = (GeneratedCode / TotalCode) * TimeSinceLastHumanReview`.
- **UI:** A heatmap in the dashboard showing which modules are becoming "alien" to the developer.

### C. Narrative Synthesis (The "Story" of the Code)
- **Concept:** Humans understand stories, not diffs.
- **Implementation:** Use LLMs to generate a "Narrative Changelog" that explains *why* the logic evolved, rather than *what* lines changed.
- **Format:** "To support X, the agent refactored Y, which now affects the Z flow."

### D. Intent-Aware Handoff
- **Concept:** When copying context for an agent, include the "Intent Manifesto" (Current Decisions + Constraints).
- **Implementation:** Automatically prepend active decisions to the context bundle.

---

## 4. Technical Strategy & Phases

### Phase 1: Decision-to-Code Linkage (Short Term)
- Update `.copyclip/intelligence.db` to support many-to-many relationships between `decisions` and `files/modules`.
- CLI: `copyclip decision link <id> --path <glob>`.
- Dashboard: Visual indicators on files that have associated decisions.

### Phase 2: The Drift Detector (Mid Term)
- Enhance `analyzer.py` to perform "Semantic Diffs".
- Feature: `copyclip audit` compares the current codebase against the `Decision Log`.
- Notification: Alert if an agent-generated PR introduces patterns marked as "Risky" or "Out of Intent".

### Phase 3: Narrative Evolution UI (Mid Term)
- Add a "Narrative" tab to the Dashboard.
- Integration: Pull Git history and run it through a "Summarizer Agent" to build the "Project Story".
- Result: A vertical timeline of logic evolution, not just file changes.

### Phase 4: Intent-Driven Constraints (Long Term)
- Generate a `.copyclip/constraints.json` that agents (like Cursor, Windsurf, or custom scripts) can read to restrict their own behavior.
- "Self-Enforcing Intent": The agent checks the constraints before proposing a change.

---

## 5. Success Metrics
- **Review Time:** Reduction in time needed for a human to confidently approve an agent's PR.
- **Recoil Rate:** Decrease in "Wait, why did the AI do this?" moments after a week of development.
- **Mental Map Clarity:** High user score in "Do you still feel you own this architecture?".
