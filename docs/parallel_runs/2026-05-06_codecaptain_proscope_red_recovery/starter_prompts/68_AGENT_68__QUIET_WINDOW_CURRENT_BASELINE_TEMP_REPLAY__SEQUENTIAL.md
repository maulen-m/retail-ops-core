# Agent 68 - Quiet-Window Current-Baseline Temp Replay

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_68_quiet_window_current_baseline_temp_replay_closeout.md`

Assigned evidence folder:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_68_evidence/`

## Mission

Replay the current production baseline in a temp DB only, using the orchestrator-frozen quiet-window copy from 2026-05-07. Prove whether the current baseline can satisfy the pinned `2026-05-04` publication surface after deterministic source-freshness and ads canonical materialization.

This is a proof lane, not a production apply lane.

## Frozen Baseline To Use

The orchestrator already performed the owner-approved short scheduler quiet window and restored schedulers immediately after copy. Do not pause or unload schedulers from this agent.

Quiet-window evidence folder:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/scheduler_quiet_window_20260507_20260507_224530/`

Frozen DB:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/scheduler_quiet_window_20260507_20260507_224530/agent68_current_baseline_20260507.db`

Expected frozen DB SHA256:

`573f75385fa777d58802cfd2e41fcd303411aa60b93304a94c5a4d130624f835`

Frozen workbook:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/scheduler_quiet_window_20260507_20260507_224530/SALES_KSP_CRM_V3.agent68_current_baseline_20260507.xlsx`

Expected frozen workbook SHA256:

`93fd17e9aa7b1a41df0d3c8063e314e61949b0166a429379b9dc7af7b4871e8c`

Required quiet-window evidence to read before replay:

- `copy.log`
- `post_pause_state.log`
- `restore.log`
- `post_restore_state.log`

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/CODECAPTAIN_AGENT65_RED_PREFLIGHT_REVIEW_20260507.md`
7. `~/Docs/Oracle/Autonomous_business/2026-05-07/170703_TASK-000_codecaptain-agent65-red-preflight-review/Answer/Code_Captain_2026-05-07_17_50_00.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_65_owner_request_preflight_activation_closeout.md`
9. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_66_agent65_db_drift_forensics_closeout.md`
10. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_66_evidence/DRIFT_FORENSICS_REPORT.md`
11. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_67_source_ads_freshness_root_cause_closeout.md`
12. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_67_evidence/SOURCE_ADS_FRESHNESS_ROOT_CAUSE_REPORT.md`
13. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_62_pinned_reproof_after_asof_fix_closeout.md`
14. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/agent_53_evidence/replay/commands_run.md`
15. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/TMUX_PING_ROUTING_INCIDENT_20260507.md`

## Write Boundary

Allowed writes:

- `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_68_quiet_window_current_baseline_temp_replay_closeout.md`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_68_evidence/**`

Allowed DB writes:

- One copied working temp DB under the Agent68 evidence folder only.
- Backup files created by materializers for that temp DB only.

Forbidden:

- Do not mutate production `~/Docs/Autonomous_business/db/app.db`.
- Do not mutate `~/Docs/Autonomous_business/excel_ui/SALES_KSP_CRM_V3.xlsx`.
- Do not edit the frozen baseline DB/workbook.
- Do not pause, unload, bootstrap, or modify schedulers.
- Do not call live APIs, browser automation, Kaspi, banks, Google, Meta, Web_automation writes, or external systems.
- Do not ask the owner for an authorization phrase.
- Do not launch production apply, Agent54, or owner-request activation.
- Do not weaken validators or treat missing ads as zero spend.

## Required Sequence

1. Write a READCHECK section into the closeout with exact files read, frozen baseline hashes, and stoplines.
2. Verify the quiet-window evidence shows:
   - all five schedulers were absent during post-pause;
   - frozen DB SHA equals expected SHA;
   - frozen workbook SHA equals expected SHA;
   - frozen DB `PRAGMA integrity_check` was `ok`;
   - schedulers were restored afterward.
3. Copy the frozen DB to:

   `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_68_evidence/agent68_current_baseline_temp_replay.db`

4. Record source, copied temp DB, and workbook SHA/mtime/size plus temp DB integrity.
5. Run pre-materialization validators on the temp DB and save stdout/stderr/exit codes.
6. Materialize policy source freshness on the temp DB only:

   ```bash
   ENABLE_C3_POLICY_MATERIALIZATION_WRITE=1 python3 scripts/materialize_policy_source_freshness.py --db <temp_db> --as-of 2026-05-04 --run-id agent68_current_baseline_20260504 --apply --backup-dir <agent68_evidence>/backups --json
   ```

7. Materialize canonical ads rows on the temp DB only, using existing source evidence. Use the repo materializer first:

   ```bash
   ENABLE_C3_ADS_SOURCE_WRITE=1 python3 scripts/materialize_ads_campaign_product_daily.py \
     --app-db <temp_db> \
     --webauto-marketing-db ~/Docs/Web_automation/runs/ab_ads_source_refresh_data_gathering/20260505_acmewear_post_0415_and_historical_daily_readonly/kaspi_marketing_gap_fill.sqlite \
     --webauto-marketing-db ~/Docs/Web_automation/runs/ab_ads_source_refresh_data_gathering/20260505_acmewear_readonly/kaspi_marketing_readonly.sqlite \
     --webauto-marketing-db ~/Docs/Web_automation/runs/ab_ads_source_refresh_data_gathering/20260505_storeb_post_0415_mapping_readonly/kaspi_marketing.sqlite \
     --webauto-marketing-db ~/Docs/Web_automation/runs/ab_ads_source_refresh_data_gathering/20260505_storeb_universal_switcher_readonly/kaspi_marketing.sqlite \
     --external-marketing-db "~/Documents/useful tables/Main crm spreadsheets/main tables/External_database/Kaspi_marketing/db/kaspi_marketing.db" \
     --stores ACMEWEAR,STOREB \
     --start 2026-01-01 \
     --end 2026-05-04 \
     --output-root <agent68_evidence>/ads_materializer_apply \
     --apply \
     --json
   ```

8. If the ads materializer cannot produce a reliable temp proof, stop `YELLOW` or `RED` with exact residuals. Do not hand-edit production or broaden quarantine.
9. Run post-materialization validators on the temp DB and save stdout/stderr/exit codes.
10. Compare before/after table counts for at least:
    - `source_freshness_result`
    - `ads_source_refresh_runs`
    - `ads_campaign_product_daily`
    - `fact_order_entry_product_identity_quarantine`
    - `fact_inventory_snapshot_size`
    - `stock_ledger`
    - `order_status_event`
    - `fact_cashflow_events`
    - `fact_cashflow_daily`
11. Prove no post-as-of leakage into the pinned proof. At minimum, record whether relevant Agent68-created rows/events have dates after `2026-05-04`; if a table is intentionally current-state and not event-dated, explain that explicitly.
12. Write a concise recommendation for Agent69:
    - exact production deltas required, if any;
    - target tables;
    - expected row deltas;
    - required SHA gates;
    - rollback plan;
    - whether CodeCaptain review should happen before any owner phrase.

## Required Validators

Run these against the temp DB and record exact command, exit code, stdout/stderr path, and interpretation:

```bash
sqlite3 -readonly <temp_db> 'PRAGMA integrity_check;'
python3 scripts/validate_operational_stock_schema.py --db <temp_db> --json
python3 scripts/validate_operational_stock_integration_gates.py --db <temp_db> --as-of 2026-05-04 --json
python3 scripts/validate_policy_source_freshness.py --db <temp_db> --as-of 2026-05-04 --strict --json
python3 scripts/validate_order_cashflow_coverage.py --db <temp_db>
python3 scripts/validate_cashflow_invariants.py --db <temp_db>
python3 scripts/validate_cashflow_actual_model_separation.py --db <temp_db>
python3 scripts/validate_ads_sidecar_readiness.py --db <temp_db> --as-of 2026-05-04 --strict --output-root <agent68_evidence>/ads_sidecar_readiness
python3 scripts/validate_ads_offer_universe_coverage.py --db-path <temp_db> --as-of 2026-05-04 --start 2026-01-01 --end 2026-05-04 --strict --output-dir <agent68_evidence>/ads_offer_universe
python3 scripts/validate_ads_spend_reality.py --db-path <temp_db> --as-of 2026-05-04 --start 2026-01-01 --end 2026-05-04 --strict --output-dir <agent68_evidence>/ads_spend_reality
```

Also run the focused tests most relevant to the materializers if practical:

```bash
python3 -m pytest tests/test_materialize_ads_campaign_product_daily.py tests/test_policy_materialization_c3.py -q
```

## Required Evidence Files

Create or populate:

- `COMMANDS_RUN.md`
- `VALIDATOR_MATRIX.tsv`
- `BEFORE_AFTER_TABLE_COUNTS.tsv`
- `SOURCE_FRESHNESS_MATERIALIZATION.json`
- `ADS_MATERIALIZER_SUMMARY.json`
- `LEAKAGE_MATRIX.tsv`
- `AGENT69_REPAIR_APPLY_CONTRACT_INPUTS.md`
- `EVIDENCE_MANIFEST.txt`

## Gate Semantics

`GREEN`:

- Frozen baseline verification passes;
- temp DB only was modified;
- source freshness and ads canonical materialization succeed;
- all required pinned `2026-05-04` validators pass;
- no post-as-of leakage compromises the pinned proof;
- production DB/workbook/schedulers/external systems remain untouched;
- Agent69 can draft a production repair/apply contract from exact deltas.

`YELLOW`:

- temp proof is useful but residuals remain;
- residuals are explainable and bounded;
- no production mutation occurred;
- Agent69 can draft a narrower repair plan or additional proof lane.

`RED`:

- production mutation occurs;
- frozen baseline evidence is invalid;
- temp replay is unreproducible;
- validators fail in a publication-risk way without bounded repair path;
- post-as-of leakage compromises the pinned proof.
