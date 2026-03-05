# Spec: CopyClip MCP - The Central Intent Authority

## 1. Vision: The "One Source of Truth"
In a multi-agent ecosystem (Claude Code, Gemini, Cursor, Codex), agents often operate in silos, leading to fragmented architectures. 

**The Goal:** Deploy CopyClip as an MCP (Model Context Protocol) Server. It will act as the **Central Intent Authority**. Any agent working on the repository must consult CopyClip to get context, ensuring all AI actions are bounded by the same human-defined decisions.

## 2. Core Architecture
- **Protocol:** Standard MCP over STDIO (for local CLI agents like Claude Code) or SSE (for remote connections).
- **Backend:** Leverages the existing `intelligence.db` and the minimization engine in `src/copyclip/`.
- **Role:** CopyClip is NOT an agent that writes code. It is an "Oracle" that provides highly compressed, intent-aware context and audits proposals.

## 3. Exposed MCP Tools

The CopyClip MCP Server will expose the following tools to external agents:

### Tool 1: `get_intent_manifesto`
- **Purpose:** The first tool an agent must call when starting a session.
- **Action:** Returns a summary of the project's soul, all `accepted`/`resolved` decisions, and high-level architectural rules.
- **Agent Prompt Mapping:** *"Before writing code, get the project's intent manifesto to ensure alignment."*

### Tool 2: `get_context_bundle`
- **Arguments:** `paths` (list of globs), `minimize_level` (basic/contextual).
- **Purpose:** Replaces the agent's raw file-reading capability with an intelligent, token-optimized reader.
- **The Magic:** If the agent requests `src/auth/login.py`, CopyClip doesn't just return the code. It returns:
  1. The linked decisions for that module (e.g., "Decision #4: Use JWT, no sessions").
  2. The minimized code.
  3. The current "Cognitive Debt" score for that file.

### Tool 3: `audit_proposal`
- **Arguments:** `proposed_diff` (string).
- **Purpose:** Allows agents to **self-audit**.
- **Workflow:** Before an agent executes a file write or presents a PR, it sends the diff to this tool. CopyClip uses its Semantic Drift Auditor to check the diff against the Intent Manifesto.
- **Response:** `{"status": "approved"}` or `{"status": "rejected", "reason": "Violates Decision #12..."}`.

### Tool 4: `log_decision_proposal`
- **Arguments:** `title`, `summary`.
- **Purpose:** If an agent realizes it needs to make an architectural choice that isn't covered by the manifesto, it can propose a decision via MCP. The human can later approve it in the CopyClip Dashboard.

## 4. Implementation Strategy

### Phase 1: The Read-Only Oracle
- Create `src/copyclip/mcp_server.py`.
- Implement MCP protocol handling (using `mcp` python package).
- Expose `get_intent_manifesto` and `get_context_bundle`.
- Integration test with Claude Desktop.

### Phase 2: The Self-Auditing Loop
- Connect the `audit_proposal` tool to the existing semantic drift logic in `analyzer.py`.
- Document standard prompts for agents (e.g., "Always run `audit_proposal` before finalizing your task").

### Phase 3: Agent Bi-directionality
- Implement `log_decision_proposal`.
- Allow agents to read the "Fog of War" map to prioritize refactoring dark areas of the codebase.

## 5. Value Proposition
By placing CopyClip at the center of the MCP ecosystem, the developer only needs to maintain their intent in ONE place (the CopyClip Dashboard). Every agent, regardless of its provider, becomes strictly bound to the developer's original vision.
