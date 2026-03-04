# Changelog

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
