# Agent905 - Order Entry Source Hierarchy Repair

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_option1_next_repair_wave/agent905_order_entry_source_hierarchy_repair_closeout.md`

Assigned evidence root:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_option1_next_repair_wave/agent905_order_entry_source_hierarchy_repair_evidence`

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-18_mvos_option1_next_repair_wave/PLAN.md`
4. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_OPTION1_NEXT_REPAIR_WAVE_20260518_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_OPTION1_NEXT_REPAIR_WAVE_20260518_STARTERS/01_AGENT_905__ORDER_ENTRY_SOURCE_HIERARCHY__PARALLEL_ROOT.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_owner_approved_green_repair/agent902_orders_lifecycle_cogs_repair_closeout.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_owner_approved_green_repair/ORCHESTRATOR_REVIEW_AFTER_901_904.md`

## Mission

Resolve or sharply classify the `177` missing recent `fact_order_entries_kaspi` rows for `STOREB`, `ACMEWEAR`, and `UNIVERSAL`.

Use only existing local evidence and copied-temp DB proof. Do not fetch externally. Do not write production DB, workbook, scheduler, source pointers, Web_automation, Kaspi/API/WebUI, or any external system.

## Source Hierarchy

Allowed local evidence classes:

- API order headers already in the repo DB/evidence;
- saved API raw order-entry evidence already on disk;
- saved WebUI archive exports already on disk;
- CRM/workbook/Google-board-derived local files as evidence only;
- Telegram/waybill bundle evidence already on disk;
- existing repo evidence and prior agent evidence.

Identity-bearing requirement:

Only create copied-temp `fact_order_entries_kaspi` rows when all of these are auditable:

- `order_id`;
- `store_code`;
- SKU/product identity;
- size or `sku_id`;
- quantity;
- source provenance path and hash or equivalent immutable local evidence.

Header-only, ambiguous, or source-missing rows must remain quarantined and visible. Do not insert header-only rows into `fact_order_entries_kaspi`.

## Required Work

1. Verify accepted DB/workbook boundary at start.
2. Copy `db/app.db` to the evidence folder and run all repair attempts against the copy only.
3. Reproduce the Agent902 order-entry freshness failure for `STOREB`, `ACMEWEAR`, and `UNIVERSAL`.
4. Inventory available local source evidence for the `177` missing rows.
5. Build a candidate matrix with one row per missing order/store pair and evidence classification:
   - `identity_bearing_repairable`;
   - `header_only_quarantine`;
   - `ambiguous_quarantine`;
   - `source_missing_quarantine`.
6. If there are repairable rows, apply them only to the copied DB using an existing safe materializer if possible. If no existing materializer can safely represent the contract, produce a contract and SQL/dry-run artifact but do not force a false green.
7. Rerun `validate_order_entries_freshness.py` on the copied DB for the three-store scope.
8. Write a closeout with `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.

## Suggested Commands

Use exact paths and adjust only evidence roots:

```bash
python3 scripts/validate_order_entries_freshness.py --db <copied-db> --as-of 2026-05-18 --lookback-days 14 --stores STOREB,ACMEWEAR,UNIVERSAL --strict
python3 scripts/recover_order_entries_from_evidence.py --db <copied-db> --as-of 2026-05-18 --start-date 2026-05-05 --target-source fact_orders_kaspi --stores STOREB,ACMEWEAR,UNIVERSAL --entry-required-only --output-root <evidence>/order_entry_recovery_dryrun --strict
```

Only use `--apply` against the copied DB, never production, and only if identity-bearing evidence is complete.

## Gate Rules

- `GREEN`: all `177` rows are resolved or non-repairable rows are accepted quarantines, and order-entry freshness passes for the declared scope without header-only leakage.
- `YELLOW`: useful classification/proof exists but some rows remain source-missing or require CodeCaptain/owner contract review.
- `RED`: protected boundary drift, production mutation, unsafe source use, hidden blocker, or false green.

## Non-Authorization

This task does not authorize production DB writes, workbook writes, scheduler changes, external writes, Kaspi/API/WebUI writes, stock changes, price changes, cash movement, PO commitment, owner publication, or production apply.
