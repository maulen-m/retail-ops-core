# Agent 69B / Launcher ID 692 - Non-Ads Operational Freshness Replay Proof

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_69b_non_ads_operational_freshness_replay_closeout.md`

Assigned evidence folder:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_69b_evidence/`

Parallel group:

`agent69abc_root`

## Mission

Determine the exact temp-only replay/materialization steps required to freshen the six non-ads operational truth tables that keep `src_ab_db_operational_truth` blocked after Agent68:

- `fact_inventory_snapshot_size`
- `stock_ledger`
- `sales_fact_v2`
- `order_status_event`
- `fact_cashflow_events`
- `fact_cashflow_daily`

This is a bounded proof lane. It must not mutate production, workbook files, schedulers, or external systems.

## Required Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/AGENT68_ORCHESTRATOR_REVIEW_20260507.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_68_quiet_window_current_baseline_temp_replay_closeout.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_68_evidence/AGENT69_REPAIR_APPLY_CONTRACT_INPUTS.md`
9. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_68_evidence/SOURCE_FRESHNESS_MATERIALIZATION_AFTER_ADS.json`
10. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/agent_53_evidence/replay/commands_run.md`
11. `~/Docs/Autonomous_business/core/ops/policy_materialization_c3.py`
12. `~/Docs/Autonomous_business/core/ops/operational_stock_daily_truth_runner.py`

Primary temp DB input:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_68_evidence/agent68_current_baseline_temp_replay.db`

Expected input SHA256:

`799b1c53a209f13e9bef155b929761be8c65125edc06b1c54e6062a048374954`

## Write Boundary

Allowed writes:

- `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_69b_non_ads_operational_freshness_replay_closeout.md`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_69b_evidence/**`

Allowed DB writes:

- One copied working temp DB under Agent69B evidence only.
- Backup files created for that temp DB only.

Forbidden:

- Do not mutate `~/Docs/Autonomous_business/db/app.db`.
- Do not mutate `~/Docs/Autonomous_business/excel_ui/SALES_KSP_CRM_V3.xlsx`.
- Do not mutate Agent68's input temp DB.
- Do not mutate scheduler state.
- Do not call live Kaspi/API/bank/Google/Meta/Web_automation/browser/external writes.
- Do not production-apply or ask owner for authorization.

## Required Work

1. Write READCHECK into the closeout.
2. Copy the Agent68 temp DB to:

   `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_69b_evidence/agent69b_operational_freshness_working.db`

3. Verify input SHA and copied DB integrity.
4. Reproduce the `src_ab_db_operational_truth` blocked status and extract the exact stale-table diagnostics from the source-freshness materializer/validator.
5. Build an inventory of repo scripts/materializers that can update the six stale tables. Do not guess. Record exact candidate commands and source inputs.
6. On the Agent69B temp DB only, run safe dry-run/probe commands first. If a write is necessary and the script supports temp-DB apply with env gate, apply only to the Agent69B temp DB.
7. After each materializer/replay step, record before/after row counts, min/max dates, and leakage relative to `2026-05-04`.
8. Rerun:

   ```bash
   python3 scripts/materialize_policy_source_freshness.py --db <agent69b_temp_db> --as-of 2026-05-04 --run-id agent69b_operational_freshness_20260504 --json
   python3 scripts/validate_policy_source_freshness.py --db <agent69b_temp_db> --as-of 2026-05-04 --strict --json
   python3 scripts/validate_operational_stock_integration_gates.py --db <agent69b_temp_db> --as-of 2026-05-04 --json
   ```

   Use `--apply` with `ENABLE_C3_POLICY_MATERIALIZATION_WRITE=1` only on the Agent69B temp DB if you need to persist observed rows for validation.
9. If a table cannot safely be freshened from existing local evidence, stop `YELLOW` and specify the missing source/contract exactly.
10. Produce Agent70 inputs:
   - exact replay commands that worked;
   - exact commands that failed and why;
   - temp table deltas;
   - whether Agent70 should combine them.

## Required Evidence Files

Create/populate:

- `READCHECK.md`
- `COMMANDS_RUN.md`
- `STALE_OPERATIONAL_TABLES_BEFORE.tsv`
- `REPLAY_CANDIDATE_SCRIPT_MATRIX.tsv`
- `TEMP_REPLAY_STEP_MATRIX.tsv`
- `STALE_OPERATIONAL_TABLES_AFTER.tsv`
- `SOURCE_FRESHNESS_BEFORE_AFTER.json`
- `VALIDATOR_BEFORE_AFTER_MATRIX.tsv`
- `LEAKAGE_MATRIX.tsv`
- `AGENT70_INPUTS_69B.md`
- `EVIDENCE_MANIFEST.txt`

## Gate Semantics

`GREEN`:

- all six stale operational tables have a safe temp replay/materializer path or are proven not to be required for the pinned May 4 surface;
- `src_ab_db_operational_truth` is fresh on the Agent69B temp proof, except for blockers owned by 69A/69C;
- no production/external mutation occurred.

`YELLOW`:

- some replay paths are proven but unresolved source/contract gaps remain;
- no unsafe mutation occurred.

`RED`:

- production/external mutation occurs;
- replay writes post-as-of facts into pinned proof incorrectly;
- stale table diagnostics cannot be reproduced or classified.
