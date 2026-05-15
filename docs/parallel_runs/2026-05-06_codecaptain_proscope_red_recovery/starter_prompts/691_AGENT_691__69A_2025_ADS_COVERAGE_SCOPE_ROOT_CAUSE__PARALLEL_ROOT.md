# Agent 69A / Launcher ID 691 - 2025 Ads Coverage Scope Root-Cause Proof

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_69a_2025_ads_coverage_scope_root_cause_closeout.md`

Assigned evidence folder:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_69a_evidence/`

Parallel group:

`agent69abc_root`

## Mission

Determine the exact root cause and safest repair path for the remaining Agent68 `542` `ADS_COVERAGE_MISSING` findings for delivered-sale dates `2025-01-01..2025-12-31`.

This is a bounded proof and diagnosis lane. It must not mutate production, workbook files, schedulers, external systems, or live ads sources.

## Required Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/AGENT68_ORCHESTRATOR_REVIEW_20260507.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_68_quiet_window_current_baseline_temp_replay_closeout.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_68_evidence/VALIDATOR_MATRIX.tsv`
9. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_68_evidence/AGENT69_REPAIR_APPLY_CONTRACT_INPUTS.md`
10. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_68_evidence/validator_logs/post/post_03_validate_operational_stock_integration_gates.stdout`
11. `~/Docs/Autonomous_business/scripts/materialize_ads_campaign_product_daily.py`
12. `~/Docs/Autonomous_business/config/ads_active_scope.yaml`
13. `~/Docs/Autonomous_business/config/ads_source_gap_quarantine.yaml`

Primary temp DB input:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_68_evidence/agent68_current_baseline_temp_replay.db`

Expected input SHA256:

`799b1c53a209f13e9bef155b929761be8c65125edc06b1c54e6062a048374954`

## Write Boundary

Allowed writes:

- `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_69a_2025_ads_coverage_scope_root_cause_closeout.md`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_69a_evidence/**`

Allowed DB writes:

- One copied working temp DB under Agent69A evidence only.
- Backup files created for that temp DB only.

Forbidden:

- Do not mutate `~/Docs/Autonomous_business/db/app.db`.
- Do not mutate `~/Docs/Autonomous_business/excel_ui/SALES_KSP_CRM_V3.xlsx`.
- Do not mutate Agent68's input temp DB.
- Do not mutate scheduler state.
- Do not write Web_automation, Meta, Kaspi, Google, banks, browser sessions, or any external system.
- Do not treat missing ads as zero spend without source-backed no-spend evidence or an explicit reviewed contract.
- Do not broaden quarantine to make validators pass.
- Do not draft owner phrase or production apply.

## Required Work

1. Write READCHECK into the closeout.
2. Copy the Agent68 temp DB to:

   `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_69a_evidence/agent69a_ads_coverage_working.db`

3. Verify input SHA and copied DB integrity.
4. Extract the `542` `ADS_COVERAGE_MISSING` findings into CSV/JSON and summarize by:
   - store;
   - month;
   - sku_key;
   - source sale date;
   - whether the SKU/store/month is inside current ads active scope.
5. Determine whether 2025 source-backed ads/no-spend evidence exists in current local evidence sources:
   - Web_automation Kaspi Marketing SQLite evidence under `~/Docs/Web_automation/runs/ab_ads_source_refresh_data_gathering/**`;
   - local external marketing DB `~/Documents/useful tables/Main crm spreadsheets/main tables/External_database/Kaspi_marketing/db/kaspi_marketing.db`;
   - repo configs and source-freshness packets.
6. On the Agent69A temp DB only, test whether the canonical ads materializer can safely cover `2025-01-01..2026-05-04` using existing evidence. Use dry-run first, then apply to the temp DB only if the dry-run is source-backed and no fake zero-spend issue appears.
7. Rerun the operational integration gate on the Agent69A temp DB:

   ```bash
   python3 scripts/validate_operational_stock_integration_gates.py --db <agent69a_temp_db> --as-of 2026-05-04 --json
   ```

8. Classify the result:
   - real evidence can repair all/some 2025 ads coverage;
   - source evidence does not exist and validator scope must be reviewed;
   - validator is over-reaching because current decision-grade publication should not require 2025 product-level ads coverage;
   - mixed outcome.
9. Produce an exact recommendation for Agent70:
   - temp deltas if any;
   - whether to include 2025 ads materialization in combined proof;
   - whether CodeCaptain must review a validator-scope contract before any production apply.

## Required Evidence Files

Create/populate:

- `READCHECK.md`
- `COMMANDS_RUN.md`
- `MISSING_2025_ADS_FINDINGS.csv`
- `MISSING_2025_ADS_SUMMARY.tsv`
- `SOURCE_EVIDENCE_COVERAGE_MATRIX.tsv`
- `MATERIALIZER_2025_DRYRUN_SUMMARY.json` if dry-run was possible
- `MATERIALIZER_2025_APPLY_SUMMARY.json` if temp apply was safe
- `VALIDATOR_BEFORE_AFTER_MATRIX.tsv`
- `AGENT70_INPUTS_69A.md`
- `EVIDENCE_MANIFEST.txt`

## Gate Semantics

`GREEN`:

- root cause is fully classified;
- either a source-backed temp repair clears the 542 findings, or a precise validator-scope contract is proven as the correct next step;
- no production/external mutation occurred;
- Agent70 has clear next inputs.

`YELLOW`:

- root cause is mostly classified but source evidence or scope decision remains incomplete;
- no unsafe inference or production mutation occurred.

`RED`:

- production/external mutation occurs;
- missing ads are converted to zero spend without evidence;
- findings cannot be reproduced or classified;
- no safe next path exists.
