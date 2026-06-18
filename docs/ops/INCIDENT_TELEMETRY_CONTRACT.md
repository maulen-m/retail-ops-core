# Incident Telemetry Contract

## Purpose
`G-OPS-01` exists to stop treating operator labor cost as a guess. `INEF-17`
stays `HYPOTHESIS` until the system has 30 days of incident telemetry with a
KZT cost line on every incident.

## Authority
- Owner decision: `OD-030`
- Placeholder rate: `5000 KZT/hour`
- Cost basis mark: `ASSUMED`
- Stable config: `config/validation/ops_incident_telemetry.json`
- Mutable ops log: `.claude/ops_incident_telemetry.csv`

## Required Incident Row
Every operational incident row must include:
- `incident_id`
- `occurred_at`
- `incident_class`
- `source_surface`
- `severity`
- `resolution_status`
- `minutes_spent`
- `cost_rate_kzt_per_hour`
- `cost_basis_mark`
- `cost_kzt`
- `owner_decision_id`
- `gate_id`
- `evidence_ref`
- `operator_notes`

`cost_kzt` is calculated as:

```text
minutes_spent / 60 * cost_rate_kzt_per_hour
```

The placeholder rate must remain marked `ASSUMED`. Do not rank labor cost
against capital fixes until the 30-day window is mature.

## Recording
Use the recorder instead of hand-editing the CSV:

```bash
.venv/bin/python scripts/record_ops_incident.py \
  --incident-class daily_shipping_automation \
  --source-surface google_ops_board_waybill_telegram \
  --severity medium \
  --minutes-spent 18 \
  --resolution-status resolved \
  --evidence-ref exports/validation/example/closeout.md \
  --operator-notes "local non-PII summary" \
  --apply
```

The recorder is dry-run by default. `--apply` is required to append.

## Validation
Build the current report with:

```bash
.venv/bin/python scripts/report_incident_telemetry.py --strict
```

Gate states:
- `ARMED`: schema, config, owner decision, and recorder path are valid, but the
  30-day telemetry window is not mature.
- `GREEN`: telemetry has been active for at least 30 days and all incident rows
  in the window carry valid KZT cost lines.
- `RED`: config, owner decision, schema, or one or more incident rows are
  invalid.

## Safety
Do not put customer PII, secrets, message contents, tokens, phone numbers, or
passwords in incident telemetry. Use evidence paths and non-PII summaries.
