#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-.}"
PORT="${2:-4333}"

cleanup() {
  pkill -f "copyclip start --path ${ROOT} --port ${PORT}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

copyclip start --path "$ROOT" --port "$PORT" >/tmp/copyclip-smoke.log 2>&1 &
sleep 2

curl -sf "http://127.0.0.1:${PORT}/api/health" >/dev/null
curl -sf "http://127.0.0.1:${PORT}/api/overview" >/dev/null
curl -sf "http://127.0.0.1:${PORT}/api/alerts" >/dev/null
curl -sf "http://127.0.0.1:${PORT}/api/export/weekly?days=7" >/dev/null
curl -sf -X POST "http://127.0.0.1:${PORT}/api/ask" -H 'Content-Type: application/json' -d '{"question":"what are top risks?"}' >/dev/null

echo "[OK] smoke_e2e passed on port ${PORT}"
