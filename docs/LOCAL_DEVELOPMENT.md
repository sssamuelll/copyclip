# Local development green path

This is the canonical local setup path for working on CopyClip from source.

It is intentionally minimal and matches the commands verified in this repository during issue #22.

## Prerequisites

- Python 3.10+
- Node.js 18+
- npm 9+

## Backend setup

From the repository root:

```bash
python3 -m pip install -e '.[dev]'
```

This installs the editable `copyclip` package, runtime dependencies, and the Python test dependencies used by the local verification flow.

## Frontend setup

From the repository root:

```bash
cd frontend
npm install
cd ..
```

## Start the dashboard

From the repository root:

```bash
copyclip start --no-open --path .
```

Notes:
- `--no-open` avoids auto-opening the browser during development or CI-like verification.
- The dashboard chooses an open port starting near `4310`.

## Reproducible smoke entrypoint

From the repository root:

```bash
./scripts/dev-smoke.sh
```

This is the current green-path verification command. It runs a lightweight, reproducible set of checks that are known to pass on the current codebase:

- backend import/install sanity via editable install with dev extras
- full backend pytest suite
- frontend production build

## Manual equivalent of the smoke script

If you want to run the same checks manually:

```bash
python3 -m pip install -e '.[dev]'
python3 -m pytest -q
npm --prefix frontend install
npm --prefix frontend run build
```

## Current scope of the green path

This document defines the smallest trustworthy local development path, not the entire final contributor experience.

Full test-suite cleanup, dependency drift resolution, and broader packaging hardening are tracked separately in issue #23.
