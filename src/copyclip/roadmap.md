# 🚀 CopyClip → Capability Roadmap

> Note: runtime/package version is currently `v0.4.0`. The milestones below describe product capability progress, not a strict semver changelog.

## Scheduled: dashboard retirement — Friday 2026-06-19

Ratified 2026-06-04 (cuaderno-shell consensus, Wave 5): the legacy App.tsx
router, the Sidebar, and the remaining dashboard pages are deleted on
2026-06-19, after every surviving route is re-homed to a tutor tool or a
side surface. Until then the dashboard is reachable only through the
cuaderno's existing toggle — it is an escape hatch, not a peer. No
indefinite coexistence.

## ✅ Completed (current shipped baseline)
- [x] **Project Memory:** Dynamic chat-first interface with component injection.
- [x] **MCP integration:** Robust server for external agent alignment and semantic auditing.
- [x] **Codebase Map:** 3D Three.js engine with Sitting Tree and Constellation algorithms.
- [x] **Vivid UX:** Interactive parallax, planetary scaling, and high-fidelity sidebar restoration.
- [x] **Project Timeline:** Unified event timeline (commits + decisions + narrative).
- [x] **Interactive Setup:** In-situ LLM configuration (DeepSeek, OpenAI, etc.) with persistence.
- [x] **Cognitive Load Tracker:** Visualizing "Unfamiliar Code" based on agentic code ratio.

---

## 🌟 Priorities (Short-Term)
1. **Interactive Artifacts:** Allow clicking Codebase Map nodes to trigger chat actions (e.g., "Summarize this module").
2. **Planning Bi-directionality:** Enable drag-and-drop between Kanban columns to update DB status.
3. **Audit Webhooks:** Automatic auditing of incoming Git commits via background workers.
4. **Enhanced 3D Layers:** Filter Codebase Map nodes by author (Human vs. Agent) or specific architectural decisions.

---

## 🛠️ Long-term capability goals (no launch date)
- [ ] **VSCode Extension:** Integrated intent-aware handoffs directly in the IDE.
- [ ] **Intent Drift Surface:** Passive detection layer that flags code regions which have drifted from registered architectural decisions. Surfaces the drift to the author for inspection; does NOT propose refactors or trigger agentic action. Refactor decisions stay with the author.
- [ ] **Multi-Repo Project Memory:** If the author ever needs to navigate multiple repos as a single cognitive surface, connect them. Currently single-repo only.
- [ ] **Exportable Constraints:** Generate `.copyclip/constraints.json` for external LLM system prompts.

---

# 🎯 Vision
A personal cognitive sentinel for the author — the tool that lets him stay attached to his own codebases as AI agents write more of the code. If others with the same pain eventually find it useful, that's downstream of the author's own daily use working.
