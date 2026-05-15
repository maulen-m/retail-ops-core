# Agent 13 - Serialized Production Apply After Agent 12

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-04_source_truth_blocker_unblock_wave2/agent_13_serial_production_apply_closeout.md`

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-04_source_truth_blocker_unblock_wave2/PLAN.md`
5. `~/Docs/Autonomous_business_agent_handoffs/2026-05-04_source_truth_blocker_unblock_wave2/agent_12_serial_temp_implementation_closeout.md`
6. this starter prompt
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-04_source_truth_blocker_unblock_wave2/ORCHESTRATOR_REVIEW_AFTER_AGENT_12.md`

## Mission

Apply the accepted Agent 12 source-backed lifecycle and PO/inbound repairs to production `~/Docs/Autonomous_business/db/app.db`.

Do not apply ads rows in this lane. Ads remain blocked because WA1 ACMEWEAR is YELLOW/partial due Kaspi Marketing `429` rate limits and WA2 STOREB closeout is not yet available. Leave ads blockers open/YELLOW and do not create fake zero-spend rows.

## Write Boundary

Production DB writes are allowed only through Agent 12 accepted commands, backup-first, with explicit env gates and `--apply`.

Forbidden:

- ad-platform writes;
- workbook edits;
- external-system writes;
- unreviewed SQL patches;
- weakening validators to pass.

## Required Flow

1. Create a timestamped production DB backup under:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-04_source_truth_blocker_unblock_wave2/db_backups/`

2. Capture pre-state counts.
3. Run Agent 12 accepted production apply commands exactly, with env gates.
4. Capture post-state counts.
5. Rerun validators.
6. Write rollback command with exact backup path.

Limited apply rule:

- run lifecycle repair production commands from Agent 12;
- run PO/inbound line-grain production commands from Agent 12;
- do not run the ads production apply commands unless a later orchestrator message explicitly authorizes it after WA closeouts are reviewed;
- if any command tries to materialize ads rows, stop and close YELLOW/RED rather than proceeding.

## Required Validators

```bash
python3 scripts/validate_operational_stock_integration_gates.py --db db/app.db --as-of 2026-05-03 --json
python3 scripts/validate_cashflow_invariants.py --db db/app.db
scripts/lint_docs.sh
scripts/check_no_db_tracked.sh
```

Add any focused tests Agent 12 identifies.

## Closeout Requirements

Your closeout must include:

- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`;
- backup path and SHA-256;
- exact apply commands;
- before/after blocker counts;
- validator results;
- rollback command;
- whether Agent 14 is safe to launch.
