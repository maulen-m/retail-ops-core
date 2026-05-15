# Agent 734 - Simulate Wrapper Full Copied-DB Proof

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_734_simulate_wrapper_full_temp_proof_closeout.md`

Assigned evidence folder:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_734_evidence/`

Parallel group:

`agent734_simulate_wrapper_full_temp_proof`

## Mission

Prove the corrected command family on a copied DB only after Agents732 and 733 found that the production-safe missing piece is the simulation snapshot wrapper path.

This is a no-production-mutation lane. Mutate only copied SQLite DBs under the assigned evidence folder. Do not mutate production DB, workbook, code, schedulers, browser, Web_automation, Kaspi/API, ads, Google, banks, or external systems.

You are not alone in the codebase. Do not revert or overwrite unrelated edits by others.

## Required Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/AGENT731_ORCHESTRATOR_REVIEW_20260508.md`
7. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/AGENT732_733_ORCHESTRATOR_REVIEW_20260508.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_732_agent731_red_root_cause_forensics_closeout.md`
9. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_733_agent731_red_temp_variant_proof_closeout.md`
10. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_733_evidence/RECOMMENDED_CORRECTED_SEQUENCE.md`
11. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_731_evidence/backups/app_pre_agent731_20260508_223146.db`

## Required Preflight

Run and record:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_apply_rebuild_snapshot_production_safe.py tests/test_rebuild_snapshot_negative_active_zero.py tests/test_validate_write_side_gating.py
python3 -m py_compile scripts/apply_rebuild_snapshot_production_safe.py scripts/rebuild_snapshot.py
python3 scripts/validate_write_side_gating.py --manifest config/write_side_gating_manifest.yaml
git status --short -- db/app.db excel_ui/SALES_KSP_CRM_V3.xlsx exports/ledger_negative_balances_2026-05-04.md
```

Stop RED if focused tests, py_compile, write-side gating, or protected-surface status fail.

## Required Full Copied-DB Sequence

Start from a fresh copy of:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_731_evidence/backups/app_pre_agent731_20260508_223146.db`

Use as-of `2026-05-04`, start date `2026-04-16`, store `UNIVERSAL`.

Run the Agent70/Variant-B sequence, but replace unsafe direct commands with production-safe wrappers:

1. `rebuild_sales_fact_v2_from_kaspi_entries.py` on copied DB.
2. `materialize_stock_ledger_sales_from_sales_fact_v2.py` on copied DB.
3. `apply_rebuild_snapshot_production_safe.py --mode simulate` on copied DB.
   - Expected existing rows: `0`
   - Expected rows created: `363`
   - Expected current stock total: `13511`
   - Expected inbound stock total: `475`
4. `materialize_order_status_events_from_kaspi_orders.py` on copied DB.
5. Initial `translate_orders_to_cashflow_events.py` and `rebuild_cashflow_calendar.py`.
6. Initial `materialize_policy_source_freshness.py`.
7. Ads materializer dry-run then apply using the same source DBs as Agent70/733.
8. `recover_order_entries_from_evidence.py`.
9. After-recovery `translate_orders_to_cashflow_events.py` and `rebuild_cashflow_calendar.py`.
10. `apply_storeb_product_identity_quarantine_production_safe.py`.
    - Expected candidate rows: `23`
    - Expected product cashflow delete rows: `2`
    - Expected stock ledger delete rows: `23`
11. `apply_header_only_source_gap_quarantine_production_safe.py`.
    - Expected candidate rows: `252`
    - Expected product cashflow delete rows: `4`
    - Expected stock ledger delete rows: `251`
    - Expected sales-fact product/profit null rows: `0`
12. Final `materialize_policy_source_freshness.py`.
13. Final pinned validators:
    - `validate_policy_source_freshness.py --as-of 2026-05-04 --strict --json`
    - `validate_operational_stock_integration_gates.py --as-of 2026-05-04 --json`
    - `validate_order_cashflow_coverage.py --as-of 2026-05-04 --strict --json`
    - `validate_cashflow_actual_model_separation.py --anchor-date 2026-05-04 --strict --json`
    - `validate_cashflow_invariants.py`

If an expected control mismatches, stop and close RED/YELLOW with evidence rather than relaxing controls.

## Required Evidence Files

Create these under assigned evidence:

1. `READCHECK.md`
2. `COMMANDS_RUN.md`
3. `FOCUSED_TEST_RESULTS.txt`
4. `WRITE_SIDE_GATING.txt`
5. `PROTECTED_SURFACE_STATUS.txt`
6. `SIMULATE_WRAPPER_SUMMARY.json`
7. `STRICT23_PROD_WRAPPER_SUMMARY.json`
8. `HEADER252_PROD_WRAPPER_SUMMARY.json`
9. `ROWCOUNT_MATRIX.tsv`
10. `VALIDATOR_MATRIX.tsv`
11. `LEAKAGE_MATRIX.tsv`
12. `ORDER_LEVEL_CASH_PRESERVATION.tsv`
13. `WARNING_VISIBILITY_MATRIX.tsv`
14. `FINAL_DB_SHA_AND_INTEGRITY.txt`
15. `RECOMMENDED_NEXT_STEP.md`

## Gate Semantics

`GREEN`:

- focused tests/py_compile/write-side gating pass;
- full copied-DB sequence completes using simulate snapshot wrapper and production-safe quarantine wrappers;
- final policy validator passes;
- final operational validator passes with only accepted warning classes;
- leakage is zero for strict/header/combined cohorts;
- order-level CASH_IN is preserved;
- final DB integrity is `ok`;
- protected production DB/workbook/export diagnostic status is clean.

`YELLOW`:

- copied-DB proof is useful but one non-production decision needs orchestrator/CodeCaptain review.

`RED`:

- protected surface touched;
- expected controls mismatch;
- wrapper or validator fails;
- leakage remains;
- warning classes disappear unexpectedly;
- evidence is incomplete.

## Closeout

Write closeout with READCHECK, files written, commands run, final validator status, wrapper summaries, mutation statement, recommended next step, and standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.
