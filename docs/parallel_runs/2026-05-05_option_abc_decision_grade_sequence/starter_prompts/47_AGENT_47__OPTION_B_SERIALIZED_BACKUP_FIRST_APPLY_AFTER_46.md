# Agent 47 - Option B Serialized Backup-First Apply After 46

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/agent_47_option_b_serialized_backup_first_apply_after_46_closeout.md`

## Dependency

Do not start until Agent 46 is complete and reviewed by the orchestrator.

Do not perform production writes unless the orchestrator review explicitly says a narrow production apply is authorized.

## Mission

Convert the reviewed Option A temp proof into a backup-first production apply only if safe. If not safe, stop at dry-run and write an exact blocker report.

## Write Boundary

Allowed only after explicit apply authorization:

- backup-first production `db/app.db` apply;
- repo code/docs/tests already proven in temp;
- assigned evidence and closeout.

Forbidden:

- workbook edits unless explicitly authorized;
- external/live writes;
- ad-platform writes;
- weakening validators;
- production apply without backup and rollback instructions.

## Required Work

1. Re-read Agent 46 review and closeout.
2. If apply is not explicitly authorized, run dry-run/validation only and close `YELLOW` or `RED`.
3. If authorized:
   - backup production `db/app.db`;
   - record backup path and SHA-256;
   - apply only reviewed changes;
   - rerun the same validators as Agent 46 on production;
   - prove protected workbook surfaces are untouched;
   - write rollback instructions.

## Expected Gate

`GREEN` only if production post-apply validators match the reviewed temp proof and all remaining limitations are intentionally bannered.

`YELLOW` if apply is safe but publication remains limited.

`RED` if production apply is not safe or any gate regresses.
