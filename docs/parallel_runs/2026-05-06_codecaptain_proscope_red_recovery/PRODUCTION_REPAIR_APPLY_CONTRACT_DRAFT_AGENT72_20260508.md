# Agent72 Production Repair Apply Contract Draft - 2026-05-08

Status: DRAFT FOR AGENT73 / CODECAPTAIN REVIEW ONLY

This contract is non-mutating. It does not authorize production apply, owner authorization request, workbook edits, scheduler edits, external-system writes, Agent64 activation, old Agent54 phrase reuse, or Option C production authority.

## Scope And Non-Authorization Banner

This document translates Agent70's copied-temp DB proof into a production repair/apply contract shape for later review. It is a review artifact only.

Allowed future target, if separately authorized later:

- DB-only production target: `~/Docs/Autonomous_business/db/app.db`

Not authorized by this draft:

- No production apply.
- No owner phrase request.
- No owner phrase generation.
- No Agent64 activation.
- No old Agent54 phrase reuse.
- No live CRM workbook mutation.
- No scheduler mutation.
- No Kaspi/API/bank/Google/Meta/ads/browser/Web_automation/external write.
- No Option C production promotion.
- No treating header-only rows as product truth.

## Agent70 Source Proof

Source proof authority for this draft:

- Agent70 closeout: `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_70_combined_current_baseline_temp_proof_closeout.md`
- Agent70 evidence root: `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_70_evidence/`
- Final temp DB: `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_70_evidence/agent70_combined_current_baseline_working.db`
- Final temp DB SHA256: `3e0250c332660c249288dff5ce6a55a109361e5e3a4b44d601d2ef81a61523d0`
- Final temp DB SQLite integrity: `ok`
- Proof boundary: pinned `2026-05-04`
- Final policy source freshness: `validate_policy_source_freshness.py --strict --as-of 2026-05-04`, exit `0`, `ok=true`
- Final operational integration: `validate_operational_stock_integration_gates.py --as-of 2026-05-04 --json`, exit `0`
- Remaining findings: warning-only `ORDER_ENTRY_PRODUCT_IDENTITY_QUARANTINED=23` and `ORDER_ENTRY_HEADER_ONLY_SOURCE_GAP_QUARANTINED=252`

Production hashes observed by Agent70 are awareness only, not apply authority:

- Agent70 observed production DB SHA: `3ceb326c00be2fcc53973143e96685fe3fecb64298c486ef20451f432cd98f02`
- Agent70 observed workbook SHA: `ff0c0e58214b24c87dac8260153a486dca0ad35d27d491821d3f75b3aaafe650`

Agent72 also observed read-only current production DB hash drift during contract drafting: `db/app.db` changed from `11692ba6316b5a697b5dc8bc1829d67a94a6243ca0f48ee1b26b1b7852ddcf5d` to `1f01d762ffd5a3b0b37ce1ebccd623d3fe6a3542c238408bc5e9d69c28fbfcf9`, while the workbook hash remained `35dcb134b773b12cc17278e426a8c775a90f45b4494257b33d99c797a2fa3521` and scoped git status for protected paths stayed clean. Agent72 ran no DB write commands. This drift is not apply authority; it reinforces that any later owner-request/apply lane must freshly freeze and review the live boundary.

Any later owner-request or apply lane must freshly freeze the then-current production DB and workbook boundary. The Agent70 observed hashes must not be reused as current production proof.

## Production Write Boundary

The only production write target contemplated by this contract is:

- `~/Docs/Autonomous_business/db/app.db`

The live workbook remains UI/input/reference only:

- `~/Docs/Autonomous_business/excel_ui/SALES_KSP_CRM_V3.xlsx`

The workbook must be hash-checked before and after any later DB-only apply. Any workbook hash change is a stopline unless a separate workbook mutation contract is reviewed and authorized.

## Explicit Non-Write Boundaries

A later apply under this contract must not write to:

- `excel_ui/SALES_KSP_CRM_V3.xlsx`
- scheduler plist/state, launchd jobs, tmux orchestration state, cron, or any automated runner state
- Kaspi merchant systems or Kaspi APIs
- Meta/Facebook/ads platforms
- Google services
- bank systems or bank import sources
- browsers or UI automation targets
- `~/Docs/Web_automation` or any Web_automation live lane
- external spreadsheets or external databases except read-only source evidence explicitly accepted by review
- `.env` or secret-bearing files
- Agent70 evidence files

Local read-only source files may be referenced only as evidence inputs. Any source refresh or external pull is outside this contract.

## Expected Table Deltas From Agent70

The later staging replay and any production apply must either reproduce these Agent70 deltas or produce a reviewed explanation before owner request or production apply.

| Table or view | Expected delta |
|---|---:|
| `source_freshness_result` | `+22` |
| `ads_source_refresh_runs` | `+365` |
| `ads_campaign_product_daily` | `+1231` |
| `sales_fact_v2` | `+1284` |
| `stock_ledger` | `+957` |
| `fact_inventory_snapshot_size` | `+363` |
| `order_status_event` | `+75` |
| `fact_cashflow_events` | `+66` |
| `fact_cashflow_daily` | `+19` |
| `fact_order_entries_kaspi` | `+758` |
| `fact_order_entry_product_identity_quarantine` | `=23` |
| `fact_order_entry_header_only_source_gap_quarantine` | `=252` |
| `view_sales_line_truth` | `+920` |

The two quarantine table counts are expected final counts on the Agent70 proof lineage, not product fact inserts. If either quarantine table already exists in production, the later contract must compare exact row identities and produce a reviewed idempotency explanation before any apply.

## Preserved Warning Language

`ORDER_ENTRY_PRODUCT_IDENTITY_QUARANTINED=23` remains a visible review-required warning. It must not be cleared, hidden, interpreted as GREEN product truth, or inserted into product-level fact entries.

`ORDER_ENTRY_HEADER_ONLY_SOURCE_GAP_QUARANTINED=252` remains a visible review-required warning. It must not be cleared, hidden, interpreted as GREEN product truth, or inserted into product-level fact entries.

The strict `23`, header-only `252`, and combined `275` warning cohorts must continue to have:

- `0` fact entries after quarantine
- `0` stock rows
- `0` product cashflow rows
- `0` product profit rows
- `0` published SKU sales-truth rows

Header-only rows are order-level cash evidence only. They are not SKU, product, COGS, product profit, stock, or published sales-line truth.

Agent70 leakage proof preserved order-level `CASH_IN` only:

- strict `23`: `24` cash-in rows, `123528.34` KZT
- header-only `252`: `256` cash-in rows, `993344.51` KZT
- combined `275`: `280` cash-in rows, `1116872.85` KZT

## Draft Command Family Controls

The command family below is a draft contract shape, not a runnable production script. It requires Agent73 and CodeCaptain/designated acceptance before it can be converted into launch commands.

Every later write command must satisfy all of these controls:

- run dry-run/preview first against a copied staging DB derived from the exact production pre-SHA;
- run production apply only after a separate owner-request preflight, reviewed owner wording, and the exact new owner authorization phrase in the launch context;
- include a reviewed global production gate such as `<REVIEW_ACCEPTED_PRODUCTION_REPAIR_GATE>`;
- include the script-specific write env gate;
- include explicit `--apply`;
- write outputs to a timestamped evidence root;
- write only `~/Docs/Autonomous_business/db/app.db`;
- perform no ad hoc SQL;
- perform no implicit migration during validation;
- stop before the first write if any placeholder remains unresolved.

If any required schema/table creation is needed in production, it must be an explicit reviewed schema/materialization step with backup, idempotency proof, and schema validation. Validators must never create or migrate tables.

## Exact Ordered Command Family - Dry Run First

All command shapes below are intentionally non-copy-paste-ready because they contain review placeholders. Agent73/CodeCaptain must accept the contract, fill exact run IDs/output roots, and decide whether each script's current env gate is sufficient for production.

Shared placeholders:

- `<PROD_DB>` = `~/Docs/Autonomous_business/db/app.db`
- `<STAGING_DB>` = copied DB built from the exact production pre-SHA
- `<EVIDENCE_ROOT>` = timestamped later evidence folder
- `<BACKUP_ROOT>` = `<EVIDENCE_ROOT>/backups`
- `<RUN_ID_PREFIX>` = reviewed later run id prefix
- `<REVIEW_ACCEPTED_PRODUCTION_REPAIR_GATE>` = not defined by Agent72; must be defined by Agent73/CodeCaptain before any production write

Dry-run family on `<STAGING_DB>`:

1. Focused tests:
   - `python3 -m pytest tests/test_recover_order_entries_from_evidence.py tests/test_header_only_source_gap_quarantine.py tests/test_operational_stock_integration_gates.py tests/test_storeb_product_identity_quarantine.py tests/test_materialize_ads_campaign_product_daily.py -q`
2. Pre-replay validators:
   - `python3 scripts/validate_policy_source_freshness.py --db <STAGING_DB> --as-of 2026-05-04 --strict --json`
   - `python3 scripts/validate_operational_stock_integration_gates.py --db <STAGING_DB> --as-of 2026-05-04 --json`
3. Sales fact rebuild preview:
   - `python3 scripts/rebuild_sales_fact_v2_from_kaspi_entries.py --db <STAGING_DB> --as-of 2026-05-04 --start-date 2026-04-16 --output-root <EVIDENCE_ROOT>/dryrun/sales_fact_v2_rebuild_0416 --backup-root <BACKUP_ROOT> --strict`
4. Stock ledger sales replay preview:
   - `python3 scripts/materialize_stock_ledger_sales_from_sales_fact_v2.py --db <STAGING_DB> --start-date 2026-04-16 --end-date 2026-05-04 --output-root <EVIDENCE_ROOT>/dryrun/stock_ledger_sales_replay`
5. Snapshot rebuild preview:
   - `python3 scripts/rebuild_snapshot.py --db <STAGING_DB> --date 2026-05-04 --store UNIVERSAL --mode simulate --compare`
6. Order-status events preview:
   - `python3 scripts/materialize_order_status_events_from_kaspi_orders.py --db <STAGING_DB> --as-of 2026-05-04 --run-id <RUN_ID_PREFIX>_order_status_events_20260504 --backup-dir <BACKUP_ROOT> --replace-run-id --strict --json`
7. Initial cashflow translation/calendar preview:
   - `python3 scripts/translate_orders_to_cashflow_events.py --db <STAGING_DB> --since 2026-04-16 --until 2026-05-04 --run-id <RUN_ID_PREFIX>_after_non_ads_contracts_20260504 --output-path <EVIDENCE_ROOT>/dryrun/orders_to_cashflow_initial_report.txt --allow-missing`
   - `python3 scripts/rebuild_cashflow_calendar.py --db <STAGING_DB> --start-date 2026-04-16 --end-date 2026-05-04 --run-id <RUN_ID_PREFIX>_cashflow_daily_initial_20260504`
8. Initial policy freshness materialization preview:
   - `python3 scripts/materialize_policy_source_freshness.py --db <STAGING_DB> --as-of 2026-05-04 --run-id <RUN_ID_PREFIX>_operational_freshness_initial_20260504 --backup-dir <BACKUP_ROOT> --json`
9. Ads materialization preview:
   - `python3 scripts/materialize_ads_campaign_product_daily.py --app-db <STAGING_DB> --webauto-marketing-db ~/Docs/Web_automation/runs/ab_ads_source_refresh_data_gathering/20260505_acmewear_post_0415_and_historical_daily_readonly/kaspi_marketing_gap_fill.sqlite --webauto-marketing-db ~/Docs/Web_automation/runs/ab_ads_source_refresh_data_gathering/20260505_acmewear_readonly/kaspi_marketing_readonly.sqlite --webauto-marketing-db ~/Docs/Web_automation/runs/ab_ads_source_refresh_data_gathering/20260505_storeb_post_0415_mapping_readonly/kaspi_marketing.sqlite --webauto-marketing-db ~/Docs/Web_automation/runs/ab_ads_source_refresh_data_gathering/20260505_storeb_universal_switcher_readonly/kaspi_marketing.sqlite --external-marketing-db '~/Documents/useful tables/Main crm spreadsheets/main tables/External_database/Kaspi_marketing/db/kaspi_marketing.db' --stores ACMEWEAR,STOREB --start 2025-01-01 --end 2026-05-04 --output-root <EVIDENCE_ROOT>/dryrun/ads_2025_2026 --json`
10. Order-entry recovery preview:
    - `python3 scripts/recover_order_entries_from_evidence.py --db <STAGING_DB> --as-of 2026-05-04 --recovery-ts 2026-05-04T23:59:59+05:00 --output-root <EVIDENCE_ROOT>/dryrun/order_entry_recovery`
11. After-recovery cashflow preview:
    - `python3 scripts/translate_orders_to_cashflow_events.py --db <STAGING_DB> --since 2026-04-16 --until 2026-05-04 --run-id <RUN_ID_PREFIX>_after_order_entry_recovery_20260504 --output-path <EVIDENCE_ROOT>/dryrun/orders_to_cashflow_after_recovery_report.txt --allow-missing`
    - `python3 scripts/rebuild_cashflow_calendar.py --db <STAGING_DB> --start-date 2026-04-16 --end-date 2026-05-04 --run-id <RUN_ID_PREFIX>_cashflow_daily_after_recovery_20260504`
12. Quarantine previews:
    - `python3 scripts/materialize_storeb_product_identity_quarantine.py --db <STAGING_DB> --candidates ~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_69e_evidence/OPTIONAL_CANDIDATE_QUARANTINE_ROWS.csv --output-root <EVIDENCE_ROOT>/dryrun/strict_23_quarantine`
    - `python3 scripts/materialize_header_only_source_gap_quarantine.py --db <STAGING_DB> --classification ~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_69e_evidence/RESIDUAL_275_ROW_CLASSIFICATION.tsv --output-root <EVIDENCE_ROOT>/dryrun/header_only_252_quarantine`
13. Final policy freshness preview:
    - `python3 scripts/materialize_policy_source_freshness.py --db <STAGING_DB> --as-of 2026-05-04 --run-id <RUN_ID_PREFIX>_final_source_freshness_20260504 --backup-dir <BACKUP_ROOT> --json`
14. Final validators on staging:
    - `python3 scripts/validate_policy_source_freshness.py --db <STAGING_DB> --as-of 2026-05-04 --strict --json`
    - `python3 scripts/validate_operational_stock_integration_gates.py --db <STAGING_DB> --as-of 2026-05-04 --json`
    - `sqlite3 <STAGING_DB> 'PRAGMA integrity_check;'`

Apply family after accepted staging proof, reviewed owner-request packet, and exact owner authorization:

1. `ENABLE_SALES_FACT_V2_REBUILD_APPLY=1 <REVIEW_ACCEPTED_PRODUCTION_REPAIR_GATE> python3 scripts/rebuild_sales_fact_v2_from_kaspi_entries.py --db <PROD_DB> --as-of 2026-05-04 --start-date 2026-04-16 --output-root <EVIDENCE_ROOT>/apply/sales_fact_v2_rebuild_0416 --backup-root <BACKUP_ROOT> --strict --apply`
2. `ENABLE_STOCK_LEDGER_SALES_REPLAY_WRITE=1 <REVIEW_ACCEPTED_PRODUCTION_REPAIR_GATE> python3 scripts/materialize_stock_ledger_sales_from_sales_fact_v2.py --db <PROD_DB> --start-date 2026-04-16 --end-date 2026-05-04 --output-root <EVIDENCE_ROOT>/apply/stock_ledger_sales_replay --apply`
3. `<REVIEW_ACCEPTED_PRODUCTION_REPAIR_GATE> <REVIEWED_SNAPSHOT_WRITE_GATE_REQUIRED> python3 scripts/rebuild_snapshot.py --db <PROD_DB> --date 2026-05-04 --store UNIVERSAL --mode simulate --compare --apply`
4. `ENABLE_ORDER_STATUS_EVENT_WRITE=1 <REVIEW_ACCEPTED_PRODUCTION_REPAIR_GATE> python3 scripts/materialize_order_status_events_from_kaspi_orders.py --db <PROD_DB> --as-of 2026-05-04 --run-id <RUN_ID_PREFIX>_order_status_events_20260504 --backup-dir <BACKUP_ROOT> --replace-run-id --apply --strict --json`
5. `ENABLE_CASHFLOW_WRITE=1 <REVIEW_ACCEPTED_PRODUCTION_REPAIR_GATE> python3 scripts/translate_orders_to_cashflow_events.py --db <PROD_DB> --since 2026-04-16 --until 2026-05-04 --run-id <RUN_ID_PREFIX>_after_non_ads_contracts_20260504 --output-path <EVIDENCE_ROOT>/apply/orders_to_cashflow_initial_report.txt --allow-missing --apply`
6. `ENABLE_CASHFLOW_WRITE=1 <REVIEW_ACCEPTED_PRODUCTION_REPAIR_GATE> python3 scripts/rebuild_cashflow_calendar.py --db <PROD_DB> --start-date 2026-04-16 --end-date 2026-05-04 --run-id <RUN_ID_PREFIX>_cashflow_daily_initial_20260504 --apply`
7. `ENABLE_C3_POLICY_MATERIALIZATION_WRITE=1 <REVIEW_ACCEPTED_PRODUCTION_REPAIR_GATE> python3 scripts/materialize_policy_source_freshness.py --db <PROD_DB> --as-of 2026-05-04 --run-id <RUN_ID_PREFIX>_operational_freshness_initial_20260504 --apply --backup-dir <BACKUP_ROOT> --json`
8. `ENABLE_C3_ADS_SOURCE_WRITE=1 <REVIEW_ACCEPTED_PRODUCTION_REPAIR_GATE> python3 scripts/materialize_ads_campaign_product_daily.py --app-db <PROD_DB> --webauto-marketing-db ~/Docs/Web_automation/runs/ab_ads_source_refresh_data_gathering/20260505_acmewear_post_0415_and_historical_daily_readonly/kaspi_marketing_gap_fill.sqlite --webauto-marketing-db ~/Docs/Web_automation/runs/ab_ads_source_refresh_data_gathering/20260505_acmewear_readonly/kaspi_marketing_readonly.sqlite --webauto-marketing-db ~/Docs/Web_automation/runs/ab_ads_source_refresh_data_gathering/20260505_storeb_post_0415_mapping_readonly/kaspi_marketing.sqlite --webauto-marketing-db ~/Docs/Web_automation/runs/ab_ads_source_refresh_data_gathering/20260505_storeb_universal_switcher_readonly/kaspi_marketing.sqlite --external-marketing-db '~/Documents/useful tables/Main crm spreadsheets/main tables/External_database/Kaspi_marketing/db/kaspi_marketing.db' --stores ACMEWEAR,STOREB --start 2025-01-01 --end 2026-05-04 --output-root <EVIDENCE_ROOT>/apply/ads_2025_2026 --apply --json`
9. `ENABLE_ORDER_ENTRY_RECOVERY_WRITE=1 <REVIEW_ACCEPTED_PRODUCTION_REPAIR_GATE> python3 scripts/recover_order_entries_from_evidence.py --db <PROD_DB> --as-of 2026-05-04 --recovery-ts 2026-05-04T23:59:59+05:00 --output-root <EVIDENCE_ROOT>/apply/order_entry_recovery --apply`
10. `ENABLE_CASHFLOW_WRITE=1 <REVIEW_ACCEPTED_PRODUCTION_REPAIR_GATE> python3 scripts/translate_orders_to_cashflow_events.py --db <PROD_DB> --since 2026-04-16 --until 2026-05-04 --run-id <RUN_ID_PREFIX>_after_order_entry_recovery_20260504 --output-path <EVIDENCE_ROOT>/apply/orders_to_cashflow_after_recovery_report.txt --allow-missing --apply`
11. `ENABLE_CASHFLOW_WRITE=1 <REVIEW_ACCEPTED_PRODUCTION_REPAIR_GATE> python3 scripts/rebuild_cashflow_calendar.py --db <PROD_DB> --start-date 2026-04-16 --end-date 2026-05-04 --run-id <RUN_ID_PREFIX>_cashflow_daily_after_recovery_20260504 --apply`
12. `ENABLE_STOREB_PRODUCT_IDENTITY_QUARANTINE_TEMP_APPLY=1 <REVIEW_ACCEPTED_PRODUCTION_REPAIR_GATE> python3 scripts/materialize_storeb_product_identity_quarantine.py --db <PROD_DB> --candidates ~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_69e_evidence/OPTIONAL_CANDIDATE_QUARANTINE_ROWS.csv --output-root <EVIDENCE_ROOT>/apply/strict_23_quarantine --apply`
13. `ENABLE_HEADER_ONLY_SOURCE_GAP_QUARANTINE_TEMP_APPLY=1 <REVIEW_ACCEPTED_PRODUCTION_REPAIR_GATE> python3 scripts/materialize_header_only_source_gap_quarantine.py --db <PROD_DB> --classification ~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_69e_evidence/RESIDUAL_275_ROW_CLASSIFICATION.tsv --output-root <EVIDENCE_ROOT>/apply/header_only_252_quarantine --apply`
14. `ENABLE_C3_POLICY_MATERIALIZATION_WRITE=1 <REVIEW_ACCEPTED_PRODUCTION_REPAIR_GATE> python3 scripts/materialize_policy_source_freshness.py --db <PROD_DB> --as-of 2026-05-04 --run-id <RUN_ID_PREFIX>_final_source_freshness_20260504 --apply --backup-dir <BACKUP_ROOT> --json`

The snapshot and quarantine env gate names above must be reviewed before production. If current scripts do not enforce production-appropriate env gates, Agent73/CodeCaptain must require a wrapper or code patch before any owner-request lane can call the contract ready.

## Backup First Requirements

Before any later owner request or production apply, the apply lane must produce a backup packet before the owner is asked and before any write command is run.

Required backup evidence:

- production DB pre-SHA from `shasum -a 256 ~/Docs/Autonomous_business/db/app.db`
- workbook pre-SHA from `shasum -a 256 ~/Docs/Autonomous_business/excel_ui/SALES_KSP_CRM_V3.xlsx`
- DB integrity from `sqlite3 ~/Docs/Autonomous_business/db/app.db 'PRAGMA integrity_check;'`
- `lsof`/sidecar proof for `db/app.db`
- timestamped backup path under `<EVIDENCE_ROOT>/backups/`
- backup SHA from `shasum -a 256 <BACKUP_DB>`
- backup integrity from `sqlite3 <BACKUP_DB> 'PRAGMA integrity_check;'`
- rollback command written before owner request

Draft rollback command shape:

- `cp -p <BACKUP_DB> ~/Docs/Autonomous_business/db/app.db`

The rollback command is not executable from this draft. It must be embedded in the later reviewed launch packet with the exact backup path and a quiet-window/holder check.

## Pre-Owner-Request Gates

All gates below must pass before anyone asks the owner for an authorization phrase:

1. Agent73/CodeCaptain or a designated reviewer accepts this production repair/apply contract.
2. Fresh production DB SHA and live workbook SHA are captured at the start of owner-request preflight.
3. Production DB `PRAGMA integrity_check` returns `ok`.
4. Protected git status for `db/app.db` and `excel_ui/SALES_KSP_CRM_V3.xlsx` is recorded.
5. `lsof` shows no unsafe holder of `db/app.db`; WAL/SHM/journal sidecars are absent or reviewed safe.
6. Fresh backup exists, backup SHA is recorded, backup integrity is `ok`, and rollback command is written.
7. A copied-temp/staging candidate is built from the exact production pre-SHA.
8. The staging candidate reproduces Agent70 or produces a reviewed-explained delta matrix.
9. Pinned `2026-05-04` validators pass; no unpinned/no-as-of validator is used as readiness proof.
10. Leakage matrix proves strict `23`, header-only `252`, and combined `275` have zero product-level leakage.
11. Order-level `CASH_IN` preservation remains intact for warning cohorts.
12. Owner-facing wording is separately reviewed and says DB-only, no workbook, no scheduler, no external writes, no Option C, no old Agent54 phrase.
13. Current visible limitations stay visible: `912298499`, `912168984`, workbook tail rows `8053-8137`, `ORDER_ENTRY_PRODUCT_IDENTITY_QUARANTINED=23`, `ORDER_ENTRY_HEADER_ONLY_SOURCE_GAP_QUARANTINED=252`, and Option C validate-only.
14. Agent64 remains inactive unless a separately reviewed lane explicitly changes that status.

## Pre-Production-Apply Gates

All gates below must pass before production apply:

1. The owner gives the exact new authorization phrase in the launch context after owner-request wording has been reviewed.
2. Production DB SHA and workbook SHA still match the accepted apply contract at apply time.
3. Production DB integrity remains `ok`.
4. No unsafe SQLite holder, WAL, SHM, journal, or sidecar condition exists.
5. Backup exists, backup SHA is recorded, and backup integrity is `ok`.
6. Apply commands exactly match the reviewed contract.
7. Global review gate, script-specific env gates, and explicit `--apply` flags are present.
8. Missing env gate or missing `--apply` stops before the first write.
9. No live workbook mutation.
10. No scheduler mutation unless separately reviewed and authorized.
11. No external writes.
12. No ad hoc SQL.
13. No broad repo refactor.
14. No implicit migrations during validation.
15. Any schema/table creation step is explicit, reviewed, idempotent, and backed up.
16. Post-apply validators pass.
17. Post-apply row-count matrix matches expected or reviewed-explained deltas.
18. Post-apply leakage matrix remains zero for product-level leakage.
19. Warning classes remain visible.
20. Release anchor is written after success.
21. If any post-apply gate fails, restore backup immediately and record rollback evidence.

## Post-Apply Validators

Minimum validator set after any later production apply:

- `sqlite3 ~/Docs/Autonomous_business/db/app.db 'PRAGMA integrity_check;'`
- `python3 scripts/validate_policy_source_freshness.py --db ~/Docs/Autonomous_business/db/app.db --as-of 2026-05-04 --strict --json`
- `python3 scripts/validate_operational_stock_integration_gates.py --db ~/Docs/Autonomous_business/db/app.db --as-of 2026-05-04 --json`
- `python3 scripts/validate_order_cashflow_coverage.py --db ~/Docs/Autonomous_business/db/app.db --as-of 2026-05-04 --strict --json`
- `python3 scripts/validate_cashflow_invariants.py --db ~/Docs/Autonomous_business/db/app.db`
- `python3 scripts/validate_cashflow_actual_model_separation.py --db ~/Docs/Autonomous_business/db/app.db --anchor-date 2026-05-04 --strict --json`
- `python3 scripts/validate_ads_sidecar_readiness.py --db ~/Docs/Autonomous_business/db/app.db --as-of 2026-05-04 --readiness-mode apply --strict --output-root <EVIDENCE_ROOT>/post_apply/ads_sidecar_readiness`
- `python3 scripts/validate_ads_offer_universe_coverage.py --db-path ~/Docs/Autonomous_business/db/app.db --truth-source db --start 2025-01-01 --end 2026-05-04 --as-of 2026-05-04 --strict --output-dir <EVIDENCE_ROOT>/post_apply/ads_offer_universe`
- `python3 scripts/validate_ads_spend_reality.py --db-path ~/Docs/Autonomous_business/db/app.db --truth-source db --start 2025-01-01 --end 2026-05-04 --as-of 2026-05-04 --strict --output-dir <EVIDENCE_ROOT>/post_apply/ads_spend_reality`
- post-apply row-count matrix matching the Agent70 table list
- post-apply leakage matrix for strict `23`, header-only `252`, and combined `275`
- order-level cash preservation matrix
- protected workbook SHA unchanged
- `git status --short -- db/app.db excel_ui/SALES_KSP_CRM_V3.xlsx`

Any failure is a rollback trigger unless the contract has a reviewed, written exception before apply.

## Post-Apply Row-Count Matrix

The later apply lane must publish a row-count matrix with at least:

- before/after existence
- before/after row count
- delta
- before/after min date
- before/after max date
- comparison against the expected Agent70 delta
- reviewed explanation for any difference

The matrix must include the same table/view set listed in "Expected Table Deltas From Agent70".

## Post-Apply Leakage Matrix

The later apply lane must publish a leakage matrix for:

- strict `23`
- header-only `252`
- combined `275`

Minimum columns:

- order id count
- fact entries after
- stock ledger after
- product cashflow after
- sales fact COGS/profit after
- published SKU sales truth after
- order cash-in rows after
- order cash-in amount KZT after
- status

Required status for each cohort: `NO_PRODUCT_LEAKAGE`.

## Release Anchor Requirements

After a successful later production apply, before any Option C promotion or owner decision-grade claim, the apply lane must write a release anchor containing:

- accepted contract path and CodeCaptain/designated review path
- owner authorization receipt path from the later launch context
- production pre-SHA and post-SHA for `db/app.db`
- workbook pre-SHA and post-SHA proving unchanged workbook
- backup path, backup SHA, backup integrity, and rollback command
- git HEAD and scoped git status
- command transcript with exact env gates and `--apply` flags
- post-apply validator outputs
- post-apply row-count matrix
- post-apply leakage matrix
- warning classes preserved
- source input hashes/paths used for local read-only source evidence
- trust banner stating what is production green, what remains warning-only, and what remains blocked
- independent reviewer handoff path

## Rollback Triggers

Rollback is required immediately if any of these occur:

- DB integrity is not `ok`.
- Production DB pre-SHA does not match the accepted apply packet at launch.
- Workbook SHA changes without separate authorization.
- Any write occurs outside `~/Docs/Autonomous_business/db/app.db`.
- A command runs without its reviewed env gate or without `--apply`.
- Any ad hoc SQL or implicit validation migration is used.
- Pinned `2026-05-04` validators fail after apply.
- Row-count matrix is missing or unexplained against expected deltas.
- Leakage matrix shows product-level leakage for strict `23`, header-only `252`, or combined `275`.
- Warning classes disappear, are downgraded, or are interpreted as product truth.
- Header-only rows are inserted into `fact_order_entries_kaspi`, stock, product cashflow, product profit, COGS, or published SKU sales truth.
- Scheduler, workbook, browser, Web_automation, Kaspi/API, ads, Google, bank, or external writes occur.

Rollback evidence must include restored DB SHA, restored DB integrity, restored protected status, and a short incident note.

## What This Contract Does Not Authorize

This contract does not authorize:

- asking the owner for an authorization phrase;
- creating an owner phrase;
- activating Agent64;
- using or reviving the old Agent54 phrase;
- production-applying Agent70 output;
- editing the live CRM workbook;
- mutating schedulers;
- writing to external systems;
- starting browser or Web_automation write flows;
- treating Agent70 temp DB as production truth;
- claiming decision-grade owner outputs;
- promoting Option C beyond validate-only;
- hiding, clearing, downgrading, or productizing the `23` and `252` warnings.

## What Agent73 Must Package For CodeCaptain

Agent73 should package this contract with enough broad context for CodeCaptain to evaluate the DB command contract inside the whole business operating system.

Minimum Agent73 packet contents:

- this Agent72 contract path;
- Agent72 closeout and evidence manifest;
- Agent70 closeout and `agent_70_evidence/` key files;
- CodeCaptain Agent70 review and repo decision memo;
- Agent70 row-count, validator, replay-step, leakage, and order-level cash preservation matrices;
- local source evidence paths and hashes used by Agent70;
- proof that production/workbook hashes in Agent70 were awareness only;
- exact stoplines before owner request and before production apply;
- stock truth and stock snapshot context;
- order, sales, cancellation, return, and quarantine context;
- ads source coverage and sidecar readiness context;
- cashflow model versus actual cash-anchor context;
- PO, inbound, cargo, supplier obligation, and owner-reserve dependencies;
- daily automation validate-only gates and Option C stoplines;
- release hygiene, backup, rollback, trust-banner, and independent-review requirements.

Agent73 must not narrow the review to only a DB patch. CodeCaptain needs to decide whether this DB-only repair/apply contract is acceptable as part of the broader operating system and whether it is sufficient to open a separate owner-request preflight lane.
