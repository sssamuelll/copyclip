#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "[copyclip] backend editable install"
python3 -m pip install -e '.[dev]'

echo "[copyclip] backend test suite"
python3 -m pytest -q

echo "[copyclip] frontend install"
npm --prefix frontend install

echo "[copyclip] frontend build"
npm --prefix frontend run build

echo "[copyclip] green-path smoke checks passed"
