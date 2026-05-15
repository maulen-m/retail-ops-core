# Agent 737 - Header-Only 252 / 249 Control Root Cause And Copied-DB Reproof

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_737_header252_249_control_reproof_closeout.md`

Assigned evidence folder:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_737_evidence/`

Parallel group:

`agent736_737_red_triage_root`

## Mission

Explain Agent735's header-only wrapper mismatch:

- expected stock-ledger deletes: `251`
- observed stock-ledger deletes: `249`

Then prove, on copied DB only, whether using a freshly derived expected-control value of `249` safely clears header-only leakage while preserving the `252` table / `251` or updated validator-warning visibility semantics.

Do not mutate production DB, live workbook, schedulers, external systems, or repo code/config.

You are not alone in the codebase. Do not revert or overwrite unrelated edits by others.

## Required Context

Read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/AGENT735_ORCHESTRATOR_REVIEW_20260509.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_735_fresh_owner_request_preflight_no_apply_after_734_closeout.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_735_evidence/HEADER252_WRAPPER_FRESH_PREFLIGHT_SUMMARY.json`
9. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_735_evidence/FRESH_LEAKAGE_MATRIX.tsv`
10. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_735_evidence/WARNING_CLASS_VISIBILITY_MATRIX.tsv`
11. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_69e_evidence/RESIDUAL_275_ROW_CLASSIFICATION.tsv`

## Allowed Writes

Only write under the assigned evidence folder and assigned closeout.

Copied DB mutation is allowed only under the assigned evidence folder.

## Required Evidence Files

Create:

1. `READCHECK.md`
2. `HEADER252_CONTROL_ROOT_CAUSE.md`
3. `THREE_NON_PRODUCT_TRUTH_ORDER_IDS.tsv`
4. `COPIED_DB_REPROOF_COMMANDS.md`
5. `HEADER252_EXPECTED_249_WRAPPER_SUMMARY.json`
6. `FINAL_POLICY_SOURCE_FRESHNESS.json`
7. `FINAL_OPERATIONAL_INTEGRATION.json`
8. `FINAL_VALIDATOR_MATRIX.tsv`
9. `FINAL_LEAKAGE_MATRIX.tsv`
10. `FINAL_WARNING_VISIBILITY_MATRIX.tsv`
11. `RECOMMENDED_CONTRACT_DECISION.md`

## Required Work

1. Start from a copy of Agent735's pre-header staging DB:
   `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_735_evidence/staging/agent735_fresh_preflight_staging.db`
2. Verify copied DB integrity before mutation.
3. Compare all `252` header-only classification order IDs to:
   - `stock_ledger.reference_id`
   - `view_sales_line_truth.order_id`
   - product-level `fact_cashflow_events.ref_id`
   - `sales_fact_v2.order_id`
4. Identify which order IDs are in the `252` classification but already absent from product truth before header-only quarantine.
5. Verify or refute the orchestrator probe that these three order IDs are absent from product truth before the header wrapper:
   - `895525090`
   - `902946701`
   - `903096003`
6. Rerun `scripts/apply_header_only_source_gap_quarantine_production_safe.py` on a copied DB only, with freshly derived expected controls. If evidence supports `249`, use `--expected-stock-ledger-delete-rows 249`.
7. Rerun final `materialize_policy_source_freshness.py` on the copied DB only if needed for final validator parity.
8. Rerun pinned validators on the copied DB:

```bash
python3 scripts/validate_policy_source_freshness.py --db <copied_db> --as-of 2026-05-04 --strict --json
python3 scripts/validate_operational_stock_integration_gates.py --db <copied_db> --as-of 2026-05-04 --json
python3 scripts/validate_order_cashflow_coverage.py --db <copied_db> --as-of 2026-05-04 --strict --json
python3 scripts/validate_cashflow_actual_model_separation.py --db <copied_db> --anchor-date 2026-05-04 --strict --json
python3 scripts/validate_cashflow_invariants.py --db <copied_db>
```

9. Produce leakage and warning visibility matrices.
10. State whether the correct next contract should use:
    - static expected stock-ledger deletes `249`;
    - dynamic expected stock-ledger deletes derived from pre-header product-truth overlap;
    - or a different stopline.

## Gate Semantics

`GREEN`:

- root cause for `249` vs `251` is row-level evidence-backed;
- copied-DB wrapper proof with the correct expected control clears leakage;
- final pinned validators pass or show only accepted warning classes;
- no production/workbook/scheduler/external mutation occurred.

`YELLOW`:

- row-level cause is clear but contract choice needs CodeCaptain/orchestrator review.

`RED`:

- leakage remains;
- validators fail after copied-DB proof;
- expected-control derivation cannot be trusted;
- any forbidden mutation occurred.

## Closeout

Write a closeout with READCHECK, files written, commands run, row-level root cause, copied-DB proof, validator summary, recommended next step, mutation statement, and standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.
