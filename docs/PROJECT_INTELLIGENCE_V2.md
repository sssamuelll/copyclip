# CopyClip V2 Blueprint: Human-in-the-Loop Operator

CopyClip is evolving from a static context-gathering tool into a **Developer Operations Center**. The goal is to maximize the "Human-in-the-Loop" aspect, helping the developer understand, simulate, and selectively assemble context before interacting with LLMs.

## Core Features (The 7 Pillars)

### 1. Project Storyteller (Narrative Documentation)
**Goal:** Generate a technical "biography" of the project that explains the *what* and *how* without reading all the code.
*   **Backend:** `/api/story`. Collects `README.md`, modules, main dependencies, and latest decisions. Sends to an LLM to generate a narrative.
*   **UI:** A "Project Atlas" page showing the AI-generated text, updated after each `analyze`.
*   **Human-in-the-Loop:** Users can refine the story manually, adding context that is persisted in the DB.

### 2. Impact Simulator (Blast Radius Analysis)
**Goal:** Visualize what breaks if a file or module is modified.
*   **Backend:** `/api/simulate-impact?path=file_path`. Recursively traverses the `dependencies` table to find dependents and dependencies, crossing this with the `risk_score`.
*   **UI:** Interactive node graph. Hovering over a file highlights its blast radius. Larger nodes = higher impact.
*   **Human-in-the-Loop:** Humans can flag nodes as "critical" to artificially inflate their weight in the simulator.

### 3. Decision Advisor (Contextual Guardrails)
**Goal:** Prevent humans or AI from suggesting solutions that contradict previous architectural decisions.
*   **Backend:** Integrated into the CLI prompt engine and `/api/assemble-context`. A fast LLM checks the task intent against the `decisions` table.
*   **UI:** Floating warnings in the Dashboard (e.g., "Warning: You are requesting Redis, but Decision #14 enforces Memcached").

### 4. Git Archaeology (Linking Why to What)
**Goal:** Connect code blocks with their underlying rationale.
*   **Backend:** `analyzer.py` extended to aggressively parse issue IDs in commit messages. `/api/archaeology?file=path` endpoint.
*   **UI:** Code viewer with a side panel revealing the originating commit, GitHub Issue, and related Architectural Decision for the selected code block.

### 5. Smart Context Scrubbing (The Context Cart)
**Goal:** Give humans granular control over what tokens are sent to the AI.
*   **Backend:** `/api/context/preview` returns mini-summaries of selected files.
*   **UI:** A "Shopping Cart" interface. Left: AI suggestions. Right: The Context Payload. Users can toggle files between `Full Code`, `Signatures Only`, or `Docstrings Only`.
*   **Human-in-the-Loop:** Real-time token counter reflecting the exact payload size.

### 6. Health & Technical Debt Heatmap
**Goal:** Help humans decide where to invest refactoring time.
*   **Backend:** Calculates `DebtScore = (Complexity * Churn) + (OpenIssues * 2)`. `/api/heatmap` endpoint.
*   **UI:** A Treemap visualization. Size = file size. Color (Green -> Red) = DebtScore.

### 7. Interactive Project Chat (RAG on Metadata)
**Goal:** Ask questions about the project history and state.
*   **Backend:** RAG system querying the SQLite DB (issues, decisions, risks, commits).
*   **UI:** Persistent chat widget in the Dashboard.

## Implementation Iterations
1. **Iteration 1: UI Revamp.** Update Dashboard layout to support the new toolset (Atlas, Context Cart, Impact).
2. **Iteration 2: Storyteller & Heatmap.** Visual tools for immediate project comprehension.
3. **Iteration 3: Context Cart.** Visual prompt assembly and token scrubbing.
4. **Iteration 4: Simulator & Advisor.** Advanced predictive capabilities and guardrails.
