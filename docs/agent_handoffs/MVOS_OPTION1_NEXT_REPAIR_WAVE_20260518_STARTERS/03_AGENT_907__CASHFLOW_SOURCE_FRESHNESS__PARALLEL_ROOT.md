# Agent907 - Cashflow And Source Freshness Integration

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_option1_next_repair_wave/agent907_cashflow_source_freshness_integration_closeout.md`

Assigned evidence root:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_option1_next_repair_wave/agent907_cashflow_source_freshness_integration_evidence`

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/KASPI_ORDER_CASHFLOW_TRACKING.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-18_mvos_option1_next_repair_wave/PLAN.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_OPTION1_NEXT_REPAIR_WAVE_20260518_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_OPTION1_NEXT_REPAIR_WAVE_20260518_STARTERS/03_AGENT_907__CASHFLOW_SOURCE_FRESHNESS__PARALLEL_ROOT.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_owner_approved_green_repair/agent901_source_cash_payment_repair_closeout.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_owner_approved_green_repair/agent903_ads_truth_mapping_repair_closeout.md`
9. `~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_owner_approved_green_repair/ORCHESTRATOR_REVIEW_AFTER_901_904.md`

## Mission

Integrate accepted copied-temp source freshness rows and repair stale cashflow-table blockers on a copied DB only.

Known prior results:

- Agent901 made `src_bank_manual_ingest` and `src_payment_evidence_root` fresh in copied-temp proof, but cashflow tables remained stale.
- Agent903 made ads source rows and ads validators green in copied-temp proof.
- Global source freshness and policy gates still need a combined replay.

## Required Work

1. Verify accepted DB/workbook boundary at start.
2. Copy `db/app.db` to the evidence folder.
3. Reproduce source freshness and policy gate blockers on the copied DB.
4. Import or rebuild only accepted copied-temp bridge rows:
   - bank/manual cash;
   - May 18 no-new-payment bridge;
   - ads source rows accepted by Agent903;
   - any other accepted registry rows that are already explicit and copied-temp only.
5. Rebuild or refresh stale cashflow derived tables on the copied DB only if existing commands support explicit copied DB target and safe write gates.
6. Rerun:
   - `validate_policy_source_freshness.py --db <copy> --as-of 2026-05-18 --strict --json`;
   - `validate_policy_gate_results.py --db <copy> --strict --json`;
   - `validate_cashflow_invariants.py --db <copy>`;
   - `validate_order_cashflow_coverage.py --db <copy> --as-of 2026-05-18 --strict --json`.
7. Produce a source-freshness matrix and policy-gate matrix that does not hide non-lane blockers.
8. Write closeout with `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.

## Suggested Commands

```bash
python3 scripts/validate_policy_source_freshness.py --db <copied-db> --as-of 2026-05-18 --strict --json
python3 scripts/materialize_copied_temp_source_freshness_bridge.py --db <copied-db> --bridge <bridge-json> --as-of 2026-05-18 --run-id agent907_bridge_dryrun --json
ENABLE_C3_POLICY_MATERIALIZATION_WRITE=1 python3 scripts/materialize_copied_temp_source_freshness_bridge.py --db <copied-db> --bridge <bridge-json> --as-of 2026-05-18 --run-id agent907_bridge_apply --apply --backup-dir <evidence>/backups --json
ENABLE_C3_POLICY_MATERIALIZATION_WRITE=1 python3 scripts/materialize_policy_gate_results.py --db <copied-db> --as-of 2026-05-18 --run-id agent907_policy_gate_apply --apply --backup-dir <evidence>/backups --json
python3 scripts/validate_policy_gate_results.py --db <copied-db> --strict --json
python3 scripts/validate_cashflow_invariants.py --db <copied-db>
python3 scripts/validate_order_cashflow_coverage.py --db <copied-db> --as-of 2026-05-18 --strict --json
```

Only run `--apply` against the copied DB.

## Gate Rules

- `GREEN`: accepted source freshness rows and cashflow derived tables are integrated on the copied DB and assigned validators pass without hiding non-lane blockers.
- `YELLOW`: useful integration exists, but blockers remain specific and visible.
- `RED`: protected boundary drift, production mutation, unaccepted bridge rows, hidden blocker, or false green.

## Non-Authorization

This task does not authorize production DB writes, workbook writes, scheduler changes, source-pointer writes, external writes, cash movement, supplier payment, owner publication, or production apply.
