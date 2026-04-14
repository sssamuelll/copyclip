# Changelog

## v0.4.0 - 2026-04-14

### Added
- Reacquaintance Mode across backend, API, CLI, and dashboard UI.
- Baseline persistence via `project_visits` and `reentry_checkpoints`.
- `copyclip report --type reacquaint` plus optional checkpoint save support.
- Realistic fixtures and end-to-end tests for context-switch scenarios.

### Changed
- Packaging and dependency declarations aligned with the current runtime and test setup.
- Local development now uses `python3 -m pip install -e '\''.[dev]'\''` as the canonical editable-install path.
- `pytest.ini` now declares asyncio test support for the MCP-related test suite.
- Local smoke verification now runs the full backend pytest suite plus the frontend build.
- Reacquaintance ranking now maps commit evidence to files actually touched by each commit.

### Fixed
- Test collection and execution drift caused by missing dev dependencies and async pytest configuration.
- MCP/runtime dependency declaration drift in packaging files.
- Documentation drift between the shipped CLI and the local development path.
- Accidental inclusion of local generated artifacts is now prevented by `.gitignore` rules.

### Test status
- 99 passed, 1 skipped.

## v0.3.0 - 2026-03-04

### Added
- Project Intelligence control plane with one-command startup (`copyclip start`).
- Dynamic dashboard with pages for Atlas, Architecture, Changes, Decisions, Risks, Issues, Ask Project, Ops Center, and Settings.
- SSE live updates (`/api/events`) for decision lifecycle events.
- Decision timeline/history (`/api/decisions/{id}/history`) and refs (`/api/decisions/{id}/refs`).
- Ask endpoint with grounding contract and mandatory citations (`/api/ask`).
- Risk trends via snapshots (`/api/risks/trends`).
- Alerting system with rules, cooldown, and events (`/api/alerts`, `/api/alerts/rules`).
- Weekly executive export (`/api/export/weekly`).
- GitHub ingest improvements for both issues and pull requests (`/api/issues`, `/api/pulls`, `/api/github/sync`).
- Health endpoint (`/api/health`).
- E2E smoke script (`scripts/smoke_e2e.sh`).

### Improved
- API consistency with pagination (`total/limit/offset`) and metadata (`meta.project`, `meta.generated_at`).
- Decision governance via quality gate: resolving decisions now requires evidence (ref or meaningful note).
- Frontend Ops UX for rule management, alert evaluation, and weekly brief generation/copy.

### Fixed
- Runtime crash from invalid async usage in server flow.
- DB compatibility migration for missing `projects.story` column.
- Settings backend gap by adding `/api/settings` alias with GET/POST support.
- Security hardening from latest local commits (path traversal/tool endpoint protections and safer agent DB handling).

### Test status
- 58 passed, 1 skipped.
