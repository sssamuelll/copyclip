# CopyClip

CopyClip is a **context compiler for AI-assisted development**.

It takes a project folder and produces a clean, token-aware, model-friendly context bundle you can send to ChatGPT/Claude/Codex (or teammates) without manual copy/paste chaos.

---

## The Real Value

Most tools just copy files. CopyClip helps you:

- **Compress context** so LLMs get signal, not noise
- **Control scope** (only relevant files/subpaths)
- **Reduce tokens** before sending prompts
- **Generate structure views** (flow/dependencies) when needed
- **Standardize handoffs** with repeatable presets and ignore rules

In short: it turns “here’s my repo, help” into a deterministic, high-quality prompt payload.

---

## Core Capabilities

- Fast directory scanning with `.copyclipignore` / `.gitignore` support
- Concurrent file reading
- Include/exclude/only filters + presets (`code`, `docs`, `styles`, `configs`)
- Minimization modes:
  - `basic`
  - `aggressive`
  - `structural`
  - `contextual` (LLM-backed with safe fallback)
- Output views:
  - `text`
  - `flow`
  - `both`
- Optional Mermaid dependency graph in contextual mode (`--with-dependencies`)
- Clipboard-first workflow + file/stdout output options
- Token counting + context window hints

---

## Install

### Option A: local editable install (recommended for development)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

Then run:

```bash
copyclip --help
```

### Option B: run directly from repo

```bash
.venv/bin/python ./copyclip --help
```

---

## Quick Start

Copy code-focused context from current folder:

```bash
copyclip . --preset code --minimize basic
```

Generate a contextual (LLM-based) minimized bundle and save to file:

```bash
copyclip . --preset code --minimize contextual --output context.txt
```

Flow-only view for Python structure:

```bash
copyclip . --preset code --view flow
```

Contextual + dependency graph:

```bash
copyclip . --preset code --minimize contextual --with-dependencies
```

Print output to stdout instead of clipboard-only workflow:

```bash
copyclip . --preset code --print
# or
copyclip . --preset code --output -
```

---

## CLI Options

- `folder` (positional): base folder (default: current directory)
- `--extension`: include a specific extension (e.g. `.py`)
- `--preset`: `code|docs|styles|configs`
- `--include`: comma-separated glob patterns to include
- `--exclude`: comma-separated glob patterns to exclude
- `--only`: restrict to specific subpaths/patterns
- `--max-file-size`: skip files bigger than N bytes (default: 10MB)
- `--concurrency`: max concurrent file reads
- `--no-progress`: disable progress bars
- `--follow-symlinks`: follow symlinks while scanning
- `--output`: write assembled output to file (`-` for stdout)
- `--print`: print assembled output to stdout
- `--minimize`: `basic|aggressive|structural|contextual`
- `--provider`: LLM provider override (for contextual mode)
- `--model`: tokenizer/model hint
- `--docstrings`: `off|generate|overwrite`
- `--doc-lang`: `en|es`
- `--view`: `text|flow|both`
- `--flow-diagram`: deprecated alias behavior (use `--view`)
- `--with-dependencies`: prepend Mermaid dependency graph (contextual mode)

---

## Project Intelligence (New)

Analyze repository intelligence data:

```bash
copyclip analyze --path .
```

Start local dashboard service:

```bash
copyclip serve --path . --port 4310
# then open http://127.0.0.1:4310
```

Track explicit decisions:

```bash
copyclip decision add --title "Adopt WebGPU first for sim" --summary "CPU fallback remains required"
copyclip decision list
copyclip decision resolve 1
```

Generate a quick human-readable report:

```bash
copyclip report --path .
```

## Typical Workflows

### 1) Debug handoff to an LLM

```bash
copyclip ./src --preset code --include "**/*.py,**/*.ts" --exclude "**/*.test.*" --minimize contextual
```

### 2) PR review context pack

```bash
copyclip . --preset code --only "src,docs" --minimize basic --output pr-context.txt
```

### 3) Architecture quick-map for Python

```bash
copyclip . --preset code --view both --output architecture.md
```

---

## Notes

- Flow diagrams are generated for Python files.
- Contextual minimization uses configured LLM provider settings and falls back safely when unavailable.
- Strict style gates in tests are opt-in (`COPYCLIP_STRICT_GATES=1`).

---

For complete help:

```bash
copyclip --help
```
