# Release Prep Checklist

## Pre-release quality
- [ ] `PYTHONPATH=src .venv/bin/python -m pytest -q` is green
- [ ] `scripts/smoke_e2e.sh . 4333` passes
- [ ] `copyclip start` works on a clean project folder

## API sanity
- [ ] `/api/health` returns `{ok:true}`
- [ ] `/api/overview`, `/api/alerts`, `/api/export/weekly`, `/api/ask` respond correctly
- [ ] Settings GET/POST (`/api/settings`) works

## Dashboard sanity
- [ ] Ops Center can create rule + evaluate alerts
- [ ] Weekly brief can be generated and copied
- [ ] Decisions quality gate blocks resolve without evidence

## Release artifacts
- [ ] README reflects current capabilities (A/B/C complete)
- [ ] Changelog notes key milestones
- [ ] Version env (`COPYCLIP_VERSION`) set for release run
