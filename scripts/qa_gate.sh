#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-.}"
PORT="${2:-4334}"

log() { echo "[QA] $*"; }

log "Running test suite..."
PYTHONPATH=src .venv/bin/python -m pytest -q

log "Running smoke e2e..."
./scripts/smoke_e2e.sh "$ROOT" "$PORT"

log "Running endpoint contract checks..."
copyclip start --path "$ROOT" --port "$PORT" >/tmp/copyclip-qa.log 2>&1 &
PID=$!
cleanup() {
  kill "$PID" >/dev/null 2>&1 || true
}
trap cleanup EXIT
sleep 2

curl -sf "http://127.0.0.1:${PORT}/api/health" >/dev/null
curl -sf "http://127.0.0.1:${PORT}/api/overview" >/dev/null
curl -sf "http://127.0.0.1:${PORT}/api/alerts/rules" >/dev/null
curl -sf "http://127.0.0.1:${PORT}/api/alerts/scheduler" >/dev/null
curl -sf "http://127.0.0.1:${PORT}/api/risks/trends" >/dev/null
curl -sf "http://127.0.0.1:${PORT}/api/export/weekly?days=7" >/dev/null
curl -sf -X POST "http://127.0.0.1:${PORT}/api/ask" -H 'Content-Type: application/json' -d '{"question":"top risks?"}' >/dev/null

log "PASS: QA gate complete."
