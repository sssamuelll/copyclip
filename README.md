# CopyClip

**Keeps you understanding your own codebase while AI agents write most of it.**

That is the whole job. Pick up any project after a week away, after 30 agent PRs, or after a context switch — CopyClip tells you what changed, why it matters, and what you should read first.

Built first for the author's own daily use, working alongside AI agents on long-lived personal codebases. Lives publicly so others with the same pain can read it, fork it, or learn from how the architecture is shaped — but the author optimizes for his own workflow first, team adoption is not currently in scope.

- Surfaces unfamiliar code: what AI wrote that you haven't reviewed.
- Project memory anchored to architectural decisions, not just commits.
- Hands off bounded scopes to agents with explicit review gates.
- Local-first. Works alongside Claude Code, Cursor, Cline, Aider.

> In development. Current version: v0.4.0. See [CHANGELOG.md](CHANGELOG.md) for shipped features.

---

## What CopyClip does

### Reacquaintance Mode
Open any project after time away and get a five-minute briefing: what changed, who changed it, which decisions were made in your absence, and which files to read first. Anchored on the most recent human-authored commit so you re-enter through code you actually wrote, not through whatever an agent touched last.

### Ask Project — evidence-first answers
Every answer is grounded in specific commits, decisions, and files. If the evidence is thin, CopyClip says so instead of confidently hallucinating. Contradictions in the codebase are flagged explicitly, not papered over.

### Cognitive Debt Navigator
Identifies modules that have drifted from your understanding — high churn, high agent-authored ratio, stale human review, missing decisions, weak test coverage. Each dark zone comes with a remediation plan: which commits to read first, which decisions to re-check, where to focus your next hour.

### Agent Handoff Contract
Before you delegate work to a coding agent, CopyClip builds a bounded handoff packet: scope, constraints, do-not-touch boundaries, review gates. When the agent reports back, CopyClip generates a review summary comparing what changed against what was declared. Scope violations and unexpected dark-zone entries surface before merge, not after.

### Codebase Map
A 3D dependency graph that scales node size by complexity and dims unfamiliar code so your eye lands on what AI touched, not on what you already know. Useful for orienting; not a replacement for reading the code.

### MCP integration
CopyClip exposes its project memory, ask, and handoff layers as MCP tools. External agents (Claude Code, Cursor, Cline, Aider) consume bounded views — enough to do their job, not enough to drag you out of ownership.

---

## Cuaderno

The cuaderno is CopyClip's main surface: you ask questions about the codebase
and an LLM tutor answers in interactive frames, grounded in code it actually
read. Every answer carries its own verdict — answers that are ungrounded,
off-target, or short on evidence are labeled as such instead of presented as
fact. The chrome mirrors the language of your question (Spanish/English).

A deterministic eval harness (`copyclip bench`) regression-tests the tutor
against a SHA-pinned corpus of questions, so answer-quality changes are
observed rather than guessed at.

See `docs/superpowers/specs/2026-05-28-copyclip-cuaderno-conversacional-design.md`
for the design. Run `copyclip start` to configure a provider and onboard.

The cuaderno runs on any configured LLM provider (Anthropic, DeepSeek, or
OpenAI) and is most reliable on Claude: agentic frame composition leans on the
model volunteering structured artifacts, which weaker models do less
consistently. Run-requests are the exception — CopyClip constructs the
playground deterministically from the resolved symbol, so the runnable artifact
appears on any provider.

---

## How it works

CopyClip runs locally. It indexes your codebase, ingests your git history, tracks architectural decisions you mark (or that agents propose), and keeps a running record of which code each human and agent has actually read or written.

Nothing leaves your machine unless you explicitly send it to a configured LLM provider for analysis.

---

## Quick Start

### 1. Install

**macOS / Linux** (one-liner):
```bash
curl -fsSL https://raw.githubusercontent.com/sssamuelll/copyclip/main/install.sh | bash
```

**Windows** (PowerShell):
```powershell
irm https://raw.githubusercontent.com/sssamuelll/copyclip/main/install.ps1 | iex
```

**With pipx** (recommended for Python developers):
```bash
pipx install "copyclip @ git+https://github.com/sssamuelll/copyclip.git"
```

**With pip** (manual):
```bash
pip install "copyclip @ git+https://github.com/sssamuelll/copyclip.git"
```

**From source** (development):
```bash
git clone https://github.com/sssamuelll/copyclip.git
cd copyclip
python3 -m pip install -e '.[dev]'
```

### 2. Update

From the CLI:
```bash
copyclip update
```

Or re-run the install script — it detects existing installations and upgrades in place.

### 3. Start

```bash
copyclip start
```

First run walks you through interactive LLM setup (DeepSeek, OpenAI, Anthropic, etc.) and performs an initial project analysis.

The clipboard context export now lives at `copyclip export`.

### 4. Local development (green path)

From source, the canonical development path is:

```bash
python3 -m pip install -e '.[dev]'
npm --prefix frontend install
./scripts/dev-smoke.sh
copyclip start --no-open --path .
```

See [`docs/LOCAL_DEVELOPMENT.md`](docs/LOCAL_DEVELOPMENT.md) for the full verified setup and current smoke-check entrypoint.

---

## Connect external agents (MCP)

Add CopyClip to your `mcp_servers` configuration:

```json
"copyclip": {
  "command": "copyclip",
  "args": ["mcp"]
}
```

Verify locally with:
```bash
copyclip mcp --help
```

---

## Security and privacy

CopyClip respects your `.copyclipignore` and `.gitignore`. No code leaves your machine unless you explicitly send it to a configured LLM provider for analysis or auditing.

---

## Roadmap

See [`src/copyclip/roadmap.md`](src/copyclip/roadmap.md) for current direction. Near-term focus: tightening the human-in-the-loop control surfaces and reducing dark-code exposure as AI velocity continues to grow.
