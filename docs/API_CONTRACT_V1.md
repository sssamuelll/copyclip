# CopyClip Intelligence API Contract v1

Status: **frozen for v0.4.x**

This document defines stable endpoint behavior for the local CopyClip intelligence service started via:

```bash
copyclip start
```

Base URL (default):
- `http://127.0.0.1:4310`

---

## Conventions

## Content types
- JSON endpoints: `application/json`
- SSE endpoint: `text/event-stream`

## Metadata
Most JSON responses include:

```json
{
  "meta": {
    "project": "<folder-name>",
    "generated_at": "<ISO-8601>"
  }
}
```

## Pagination
List endpoints support:
- `limit` (default 100, max 500)
- `offset` (default 0)

Paginated response shape:

```json
{
  "items": [],
  "total": 0,
  "limit": 100,
  "offset": 0,
  "meta": {}
}
```

## Error shape
Common pattern:

```json
{
  "error": "error_code",
  "message": "human-readable detail"
}
```

---

## Health & Service

### GET `/api/health`
Returns service liveness.

Response:
```json
{
  "ok": true,
  "service": "copyclip-intelligence",
  "version": "dev",
  "meta": {}
}
```

### GET `/api/events?cursor=0`
Server-Sent Events stream.

Events emitted include:
- `connected`
- `decision.created`
- `decision.status_changed`
- `decision.ref_added`
- `alerts.fired`
- `github.sync.completed`

---

## Core Overview

### GET `/api/overview`
Returns current project KPI snapshot.

Fields:
- `files`, `commits`, `decisions`, `modules`, `risks`, `issues`, `pulls`
- `story`
- `meta`

### GET `/api/architecture/graph`
Returns module graph.

```json
{
  "nodes": [{"name": "..."}],
  "edges": [{"from": "...", "to": "...", "type": "import"}],
  "meta": {}
}
```

### GET `/api/files?limit=&offset=`
Paginated file inventory:
- `path`
- `size`
- `language`

### GET `/api/changes?limit=&offset=`
Paginated commit timeline:
- `sha`
- `author`
- `message`
- `date`

---

## Risks

### GET `/api/risks?limit=&offset=`
Paginated risk items:
- `area`
- `severity` (`low|med|high`)
- `kind` (`churn|test_gap|complexity|...`)
- `rationale`
- `score`
- `created_at`

### GET `/api/risks/trends`
Snapshot trend comparison.

```json
{
  "latest": {"churn": 3},
  "previous": {"churn": 1},
  "delta": {"churn": 2},
  "has_previous": true,
  "meta": {}
}
```

---

## Decisions

### GET `/api/decisions?limit=&offset=`
Paginated decisions:
- `id`, `title`, `summary`, `status`, `source_type`, `created_at`

### POST `/api/decisions`
Create decision.

Body:
```json
{"title": "...", "summary": "..."}
```

### PATCH `/api/decisions/{id}`
Update status.

Body:
```json
{"status": "accepted|resolved|superseded|proposed|unresolved", "note": "optional evidence note"}
```

Quality gate:
- resolving (`status=resolved`) requires at least one decision ref OR meaningful note.
- otherwise returns `409`:

```json
{
  "error": "quality_gate_blocked",
  "message": "Resolution requires evidence: at least one ref or a meaningful note.",
  "decision_id": 123
}
```

### GET `/api/decisions/{id}/refs`
Returns decision references.

### POST `/api/decisions/{id}/refs`
Add reference.

Body:
```json
{"ref_type": "file|commit|doc", "ref_value": "..."}
```

### GET `/api/decisions/{id}/history?limit=&offset=`
Returns decision timeline events.

---

## Ask

### POST `/api/ask`
Grounded Q&A over indexed artifacts.

Body:
```json
{"question": "..."}
```

Response:
```json
{
  "answer": "...",
  "citations": [
    {"type": "decision|risk|commit", "id": "...", "label": "..."}
  ],
  "grounded": true,
  "meta": {}
}
```

If evidence is insufficient, returns grounded=false with empty citations.

---

## Alerts

### GET `/api/alerts?limit=&offset=`
Evaluates active rules and returns:
- `fired` (newly triggered in this call)
- `events` (paginated alert history)
- `total/limit/offset`

### GET `/api/alerts/rules`
List current alert rules.

### POST `/api/alerts/rules`
Create/upsert a rule.

Body:
```json
{
  "name": "rule-name",
  "kind": "optional",
  "severity": "optional",
  "min_score": 70,
  "cooldown_min": 60,
  "enabled": true
}
```

### PATCH `/api/alerts/rules/{id}`
Partial update of existing rule.

### DELETE `/api/alerts/rules/{id}`
Delete existing rule.

### GET `/api/alerts/scheduler`
Scheduler state:
- `enabled`
- `interval_sec`
- `last_run_at`

### POST `/api/alerts/scheduler`
Update scheduler config.

Body (partial allowed):
```json
{"enabled": true, "interval_sec": 300}
```

---

## GitHub Integration

### GET `/api/issues?limit=&offset=`
Paginated ingested GitHub issues.

### GET `/api/pulls?limit=&offset=`
Paginated ingested GitHub pull requests.

### POST `/api/github/sync`
Runs analyzer sync (issues + pulls + project refresh).

---

## Export

### GET `/api/export/weekly?days=7`
Returns executive markdown brief + structured summary.

```json
{
  "markdown": "# Weekly Executive Brief ...",
  "summary": {
    "days": 7,
    "commits": 0,
    "issues": 0,
    "pulls": 0,
    "open_decisions": 0,
    "top_risks_count": 0,
    "recent_alerts_count": 0
  },
  "meta": {}
}
```

---

## Settings

### GET `/api/config`
### POST `/api/config`
### GET `/api/settings`
### POST `/api/settings`

`/api/settings` is an alias for `/api/config`.

Config body shape:
```json
{
  "COPYCLIP_LLM_PROVIDER": "gemini",
  "OPENAI_API_KEY": "..."
}
```

---

## Deprecated / internal notes
- None formally deprecated in v1.
- Future schema changes should preserve backward compatibility within `v0.4.x`.
