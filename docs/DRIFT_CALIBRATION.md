# Identity Drift Calibration (v1.1)

This document records the calibration baseline for drift metrics used by CopyClip.

## Metrics

- `decision_alignment_score` = % of decisions in `accepted|resolved`
- `architecture_cohesion_delta` = `dependency_count / module_count`
- `risk_concentration_index` = `% risk mass in top 3 risk scores`

## Thresholds (v1.1)

```json
{
  "decision_alignment_low": 55.0,
  "architecture_cohesion_high": 18.0,
  "risk_concentration_high": 65.0
}
```

## Drift Level Rule

- `high`: 2+ triggered causes
- `med`: 1 triggered cause
- `low`: 0 triggered causes

## QA Traceability

Each `identity_drift_snapshots.summary_json` includes:

- `calibration_version`
- `thresholds`
- `qa.decision_count`
- `qa.dependency_count`
- `qa.module_count`
- `qa.risk_sample_size`
- `qa.risk_total`

This allows retrospective threshold review without re-running old analyses.
