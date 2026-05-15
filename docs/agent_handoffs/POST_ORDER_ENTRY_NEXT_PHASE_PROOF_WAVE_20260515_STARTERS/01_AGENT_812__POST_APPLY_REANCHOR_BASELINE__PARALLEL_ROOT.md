# Agent812 - Post-Apply Re-Anchor Baseline

Gate target: `GREEN` if the current production boundary is re-anchored to the new post-apply DB SHA with clean protected-surface evidence and no mutation.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-15_post_order_entry_next_phase_proof_wave/PLAN.md`
4. `~/Docs/Autonomous_business/docs/agent_handoffs/POST_ORDER_ENTRY_NEXT_PHASE_PROOF_WAVE_20260515_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
5. `~/Docs/Autonomous_business/exports/validation/db_order_entry_owner_apply/20260515_091102_authorized_db_only_order_entry_apply/DB_ORDER_ENTRY_PRODUCTION_APPLY_CLOSEOUT.md`
6. this starter prompt

Sibling Agents813-816 are parallel. Do not wait for them.

## Assignment

Create the post-apply re-anchor baseline for DB SHA:

`9702c20cad71b808e52cf746c8574506aafe3f1f4d18fc6a2c48ee4880f98816`

Write evidence only under:

`~/Docs/Autonomous_business/exports/validation/post_order_entry_next_phase_proof_wave/20260515_0920/agent812_reanchor_baseline/`

Required output:

`~/Docs/Autonomous_business/exports/validation/post_order_entry_next_phase_proof_wave/20260515_0920/agent812_reanchor_baseline/POST_APPLY_REANCHOR_BASELINE.md`

Closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-15_post_order_entry_next_phase_proof_wave/agent812_post_apply_reanchor_baseline_closeout.md`

## Required Checks

- `shasum -a 256 db/app.db excel_ui/SALES_KSP_CRM_V3.xlsx`
- `sqlite3 -readonly db/app.db 'PRAGMA integrity_check;'`
- `lsof db/app.db excel_ui/SALES_KSP_CRM_V3.xlsx || true`
- SQLite sidecar check for `db/app.db-wal`, `db/app.db-shm`, `db/app.db-journal`
- `python3 scripts/manage_business_automation.py status --scope all-business --json --output-json <evidence>/business_automation_status_all_business.json`
- order-entry freshness validator summaries from the production apply closeout, plus rerun if cheap and safe
- protected-surface git status for `db/app.db` and `excel_ui/SALES_KSP_CRM_V3.xlsx`

Do not run `manage_business_automation.py verify`.

## Boundaries

Read-only except assigned evidence and closeout. No production DB writes, workbook writes, scheduler changes, external writes, owner publication, cash, PO, ads, price, stock, or lifecycle/status mutation.

Gate: GREEN
