# Agent820 - WebUI Lifecycle/Status Copied-Temp Proof

Gate target: `GREEN` if the Agent815 explicit WebUI merged CSV proves lifecycle/status materialization on a copied DB with exact before/after effects.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-15_mvos_execution_wave/PLAN.md`
4. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_EXECUTION_WAVE_20260515_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
5. `~/Docs/Autonomous_business_agent_handoffs/2026-05-15_post_order_entry_next_phase_proof_wave/agent815_webui_archive_lifecycle_status_closeout.md`
6. this starter prompt

## Assignment

Use this explicit source path, not the dirty production anchor file:

`~/Docs/Autonomous_business/exports/validation/post_order_entry_next_phase_proof_wave/20260515_0920/agent815_webui_archive_lifecycle_status/source_refresh_runs/agent815_import_existing_20260515_0920/final_merged/ArchiveOrders_WEBUI_MERGED_ALL_STORES.csv`

Evidence root:

`~/Docs/Autonomous_business/exports/validation/mvos_execution_wave/20260515_111124/agent820_webui_lifecycle_status_copy_proof/`

Required report:

`WEBUI_LIFECYCLE_STATUS_COPY_PROOF.md`

Closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-15_mvos_execution_wave/agent820_webui_lifecycle_status_copy_proof_closeout.md`

## Required Checks

- Copy `db/app.db` into your evidence root.
- Prove coverage for the current DB lifecycle/status gap, including the `635/635` matched pairs and non-empty `status_change_at` evidence.
- Separate WebUI `status_change_at` lifecycle truth from API courier/shipped truth.
- Preserve that current DB max `fact_orders_kaspi.created_at` was `2026-05-14`; new May 15 rows need fresh read-only export/import before use.

## Boundaries

Copied DB and local evidence only. No production DB apply, workbook mutation, scheduler mutation, Web_automation mutation, external write, owner publication, cash, PO, ads, price, stock, or source-pointer mutation.

Gate: GREEN
