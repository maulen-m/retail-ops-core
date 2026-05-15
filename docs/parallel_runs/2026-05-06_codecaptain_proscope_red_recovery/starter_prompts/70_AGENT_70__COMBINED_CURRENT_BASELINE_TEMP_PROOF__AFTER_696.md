# Agent 70 - Combined Current-Baseline Temp Proof

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_70_combined_current_baseline_temp_proof_closeout.md`

Assigned evidence folder:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_70_evidence/`

Parallel group:

`agent70_combined_temp_proof`

## Mission

Build the combined current-baseline temp proof from the reviewed Agent68 lineage through all accepted repair slices:

1. Agent69B non-ads operational freshness replay.
2. Agent69A 2025 ads coverage repair.
3. Agent69D `758` as-of-safe order-entry recovery.
4. Agent69E/69C strict `23` API-backed product-identity quarantine.
5. Agent696 header-only `252` source-gap quarantine.
6. D1 cashflow translation/daily rebuild after order-entry recovery.
7. Final pinned `2026-05-04` validators and leakage proofs.

This is a temp-proof lane only. It must not mutate production, workbook, schedulers, or external systems.

You are not alone in the codebase. Do not revert or overwrite unrelated edits by others.

## Required Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/AGENT68_ORCHESTRATOR_REVIEW_20260507.md`
7. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/AGENT69ABC_ORCHESTRATOR_REVIEW_20260508.md`
8. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/AGENT69DE_ORCHESTRATOR_REVIEW_20260508.md`
9. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/AGENT696_ORCHESTRATOR_REVIEW_20260508.md`
10. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_69a_evidence/AGENT70_INPUTS_69A.md`
11. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_69b_evidence/AGENT70_INPUTS_69B.md`
12. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_69d_evidence/AGENT70_INPUTS_69D.md`
13. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_69e_evidence/AGENT70_INPUTS_69E.md`
14. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_696_evidence/AGENT70_INPUTS_696.md`

Primary starting temp DB:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_68_evidence/agent68_current_baseline_temp_replay.db`

Expected starting SHA256:

`799b1c53a209f13e9bef155b929761be8c65125edc06b1c54e6062a048374954`

## Write Boundary

Allowed writes:

- `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_70_combined_current_baseline_temp_proof_closeout.md`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_70_evidence/**`

Allowed DB writes:

- one copied Agent70 temp DB under the Agent70 evidence folder;
- backup files for that copied temp DB only.

Forbidden:

- Do not mutate `~/Docs/Autonomous_business/db/app.db`.
- Do not mutate `~/Docs/Autonomous_business/excel_ui/SALES_KSP_CRM_V3.xlsx`.
- Do not mutate Agent68/69/696 source DBs or evidence files.
- Do not mutate scheduler state.
- Do not call live Kaspi/API/bank/Google/Meta/Web_automation/browser/external writes.
- Do not production-apply.
- Do not ask owner for authorization.
- Do not insert header-only rows into `fact_order_entries_kaspi`.
- Do not fabricate API evidence or silently clear quarantine warnings.

## Required Work

1. Write READCHECK into the closeout.
2. Copy the Agent68 starting temp DB into:

   `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_70_evidence/agent70_combined_current_baseline_working.db`

3. Verify starting SHA and copied DB integrity.
4. Run focused preflight tests and record output:

   ```bash
   python3 -m pytest tests/test_recover_order_entries_from_evidence.py tests/test_header_only_source_gap_quarantine.py tests/test_operational_stock_integration_gates.py tests/test_storeb_product_identity_quarantine.py tests/test_materialize_ads_campaign_product_daily.py -q
   ```

5. Reproduce the initial Agent68 validator state on the Agent70 copied DB.
6. Apply Agent69B non-ads replay sequence to the Agent70 copied DB:

   ```bash
   ENABLE_SALES_FACT_V2_REBUILD_APPLY=1 python3 scripts/rebuild_sales_fact_v2_from_kaspi_entries.py --db <agent70_temp_db> --as-of 2026-05-04 --start-date 2026-04-16 --output-root <agent70_evidence>/replay/sales_fact_v2_rebuild_apply_0416 --backup-root <agent70_evidence>/backups --strict --apply
   ENABLE_STOCK_LEDGER_SALES_REPLAY_WRITE=1 python3 scripts/materialize_stock_ledger_sales_from_sales_fact_v2.py --db <agent70_temp_db> --start-date 2026-04-16 --end-date 2026-05-04 --output-root <agent70_evidence>/replay/stock_ledger_sales_replay_apply --apply
   python3 scripts/rebuild_snapshot.py --db <agent70_temp_db> --date 2026-05-04 --store UNIVERSAL --mode simulate --compare --apply
   ENABLE_ORDER_STATUS_EVENT_WRITE=1 python3 scripts/materialize_order_status_events_from_kaspi_orders.py --db <agent70_temp_db> --as-of 2026-05-04 --run-id agent70_order_status_events_20260504 --backup-dir <agent70_evidence>/backups --replace-run-id --apply --strict --json
   ENABLE_CASHFLOW_WRITE=1 python3 scripts/translate_orders_to_cashflow_events.py --db <agent70_temp_db> --since 2026-04-16 --until 2026-05-04 --run-id agent70_after_non_ads_contracts_20260504 --output-path <agent70_evidence>/replay/orders_to_cashflow_initial_apply_report.txt --allow-missing --apply
   ENABLE_CASHFLOW_WRITE=1 python3 scripts/rebuild_cashflow_calendar.py --db <agent70_temp_db> --start-date 2026-04-16 --end-date 2026-05-04 --run-id agent70_cashflow_daily_initial_20260504 --apply
   ENABLE_C3_POLICY_MATERIALIZATION_WRITE=1 python3 scripts/materialize_policy_source_freshness.py --db <agent70_temp_db> --as-of 2026-05-04 --run-id agent70_operational_freshness_initial_20260504 --apply --backup-dir <agent70_evidence>/backups --json
   ```

7. Apply Agent69A ads coverage repair with dry-run first, then temp apply only:

   ```bash
   ENABLE_C3_ADS_SOURCE_WRITE=1 python3 scripts/materialize_ads_campaign_product_daily.py --app-db <agent70_temp_db> --webauto-marketing-db ~/Docs/Web_automation/runs/ab_ads_source_refresh_data_gathering/20260505_acmewear_post_0415_and_historical_daily_readonly/kaspi_marketing_gap_fill.sqlite --webauto-marketing-db ~/Docs/Web_automation/runs/ab_ads_source_refresh_data_gathering/20260505_acmewear_readonly/kaspi_marketing_readonly.sqlite --webauto-marketing-db ~/Docs/Web_automation/runs/ab_ads_source_refresh_data_gathering/20260505_storeb_post_0415_mapping_readonly/kaspi_marketing.sqlite --webauto-marketing-db ~/Docs/Web_automation/runs/ab_ads_source_refresh_data_gathering/20260505_storeb_universal_switcher_readonly/kaspi_marketing.sqlite --external-marketing-db '~/Documents/useful tables/Main crm spreadsheets/main tables/External_database/Kaspi_marketing/db/kaspi_marketing.db' --stores ACMEWEAR,STOREB --start 2025-01-01 --end 2026-05-04 --output-root <agent70_evidence>/replay/ads_2025_2026_apply --apply --json
   ```

8. Apply Agent69D order-entry recovery with pinned timestamp:

   ```bash
   ENABLE_ORDER_ENTRY_RECOVERY_WRITE=1 python3 scripts/recover_order_entries_from_evidence.py --db <agent70_temp_db> --as-of 2026-05-04 --recovery-ts 2026-05-04T23:59:59+05:00 --output-root <agent70_evidence>/replay/order_entry_recovery_apply --apply
   ```

9. Rerun D1 cashflow translation and daily rebuild after order-entry recovery:

   ```bash
   ENABLE_CASHFLOW_WRITE=1 python3 scripts/translate_orders_to_cashflow_events.py --db <agent70_temp_db> --since 2026-04-16 --until 2026-05-04 --run-id agent70_after_order_entry_recovery_20260504 --output-path <agent70_evidence>/replay/orders_to_cashflow_after_recovery_report.txt --allow-missing --apply
   ENABLE_CASHFLOW_WRITE=1 python3 scripts/rebuild_cashflow_calendar.py --db <agent70_temp_db> --start-date 2026-04-16 --end-date 2026-05-04 --run-id agent70_cashflow_daily_after_recovery_20260504 --apply
   ```

10. Apply the strict `23` API-backed product-identity quarantine:

   ```bash
   ENABLE_STOREB_PRODUCT_IDENTITY_QUARANTINE_TEMP_APPLY=1 python3 scripts/materialize_storeb_product_identity_quarantine.py --db <agent70_temp_db> --candidates ~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_69e_evidence/OPTIONAL_CANDIDATE_QUARANTINE_ROWS.csv --output-root <agent70_evidence>/replay/strict_23_quarantine_apply --apply
   ```

11. Apply the header-only `252` source-gap quarantine:

   ```bash
   ENABLE_HEADER_ONLY_SOURCE_GAP_QUARANTINE_TEMP_APPLY=1 python3 scripts/materialize_header_only_source_gap_quarantine.py --db <agent70_temp_db> --classification ~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_69e_evidence/RESIDUAL_275_ROW_CLASSIFICATION.tsv --output-root <agent70_evidence>/replay/header_only_252_quarantine_apply --apply
   ```

12. Refresh policy source freshness after all materialization:

   ```bash
   ENABLE_C3_POLICY_MATERIALIZATION_WRITE=1 python3 scripts/materialize_policy_source_freshness.py --db <agent70_temp_db> --as-of 2026-05-04 --run-id agent70_final_source_freshness_20260504 --apply --backup-dir <agent70_evidence>/backups --json
   ```

13. Run final validators and preserve JSON:

   ```bash
   python3 scripts/validate_policy_source_freshness.py --db <agent70_temp_db> --as-of 2026-05-04 --strict --json
   python3 scripts/validate_operational_stock_integration_gates.py --db <agent70_temp_db> --as-of 2026-05-04 --json
   ```

14. Prove leakage:
   - strict `23`: no fact entries, stock, product cashflow, product profit, or published SKU sales truth leakage;
   - header-only `252`: no fact entries, stock, product cashflow, product profit, or published SKU sales truth leakage;
   - order-level cash-in preserved.
15. Produce CodeCaptain review inputs and recommended next lane.

## Expected Final Shape

If the combined proof succeeds:

- `validate_policy_source_freshness.py --strict`: `ok=true`
- `ORDER_ENTRY_MISSING=0`
- `ADS_COVERAGE_MISSING=0`
- `CASHFLOW_D1_CASH_IN_MISSING=0`
- visible warning count includes `ORDER_ENTRY_PRODUCT_IDENTITY_QUARANTINED=23`
- visible warning count includes `ORDER_ENTRY_HEADER_ONLY_SOURCE_GAP_QUARANTINED=252`
- no product-level leakage from quarantined rows

If any RED finding remains, do not hide it. Classify it exactly and set gate `YELLOW` or `RED`.

## Required Evidence Files

Create/populate:

- `READCHECK.md`
- `COMMANDS_RUN.md`
- `INPUT_SHA_AND_INTEGRITY.txt`
- `FOCUSED_TEST_RESULTS.txt`
- `REPLAY_STEP_MATRIX.tsv`
- `TABLE_ROWCOUNT_MATRIX.tsv`
- `VALIDATOR_BEFORE_AFTER.json`
- `FINAL_POLICY_SOURCE_FRESHNESS.json`
- `FINAL_OPERATIONAL_INTEGRATION_GATE.json`
- `ORDER_ENTRY_RECOVERY_SUMMARY.json`
- `ADS_REPAIR_SUMMARY.json`
- `CASHFLOW_AFTER_RECOVERY_SUMMARY.md`
- `STRICT_23_QUARANTINE_SUMMARY.json`
- `HEADER_ONLY_252_QUARANTINE_SUMMARY.json`
- `LEAKAGE_MATRIX.tsv`
- `ORDER_LEVEL_CASH_PRESERVATION.tsv`
- `CODECAPTAIN_REVIEW_PACKET.md`
- `AGENT71_INPUTS.md`
- `EVIDENCE_MANIFEST.txt`

## Gate Semantics

`GREEN`:

- combined temp proof clears all RED findings for the pinned `2026-05-04` publication surface;
- only accepted warnings remain visible;
- policy source freshness is strict green;
- no production/external mutation occurred;
- CodeCaptain review packet is ready.

`YELLOW`:

- combined proof is mostly built but one or more classified RED findings remain;
- evidence supports a narrow follow-up lane;
- no unsafe mutation occurred.

`RED`:

- production/external mutation occurs;
- row counts diverge without explanation;
- hidden/fabricated product identity is introduced;
- quarantines silently clear instead of warning;
- validators fail in an unclassified way.
