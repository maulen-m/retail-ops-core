# Agent800 - Order Entry Copied-Temp Recovery Replay

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-13_autonomous_phase0_4_next_source_truth_wave/agent800_order_entry_copied_temp_replay_20260513_213825_closeout.md`

## Bootstrap

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/ORCHESTRATOR_REVIEW_AGENT799_RED_ACCEPTANCE_AND_PHASE0_4_LAUNCH_20260513_213825.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/AUTONOMOUS_PHASE0_4_NEXT_SOURCE_TRUTH_WAVE_PLAN_20260513_213825.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/AUTONOMOUS_PHASE0_4_NEXT_SOURCE_TRUTH_WAVE_HANDOFF_20260513_213825.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-13_autonomous_phase0_3_source_truth_wave/agent799_synthesis_20260513_192243_closeout.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-13_autonomous_phase0_3_source_truth_wave/agent794_order_entry_source_packet_20260513_192243_closeout.md`
8. `~/Docs/Autonomous_business/docs/agent_handoffs/AUTONOMOUS_PHASE0_4_NEXT_SOURCE_TRUTH_WAVE_STARTERS_20260513_213825/01_AGENT_800__ORDER_ENTRY_COPIED_TEMP_REPLAY__AFTER_799.md`

## Mission

Run the next safe order-entry copied-temp replay against the accepted Agent799 boundary:

- DB SHA: `40d21f643caefc38270427096ee615fe0667f7d90b628acf5da56d080ad783d1`
- Workbook SHA: `e7ff6fd8da8938b3247343a58e1257c102ac1d62077f68f33ad7a5b8a45ec870`

Use Agent794's source packet:

`~/Docs/Autonomous_business/exports/validation/autonomous_phase0_3_source_truth_wave/20260513_192243/agent794_order_entry_source_packet/kaspi_archive_history_20260505_to_20260513_capture`

## Scope

Allowed:

- Read repo files and Agent794/Agent799 artifacts.
- Write only under:
  `~/Docs/Autonomous_business/exports/validation/autonomous_phase0_4_next_source_truth_wave/20260513_213825/agent800_order_entry_copied_temp_replay/`
- Create and mutate a copied DB only under that evidence root.
- Run validators against the copied DB and write outputs under the evidence root.
- Write the assigned closeout.

Forbidden:

- Production `db/app.db` mutation.
- Protected workbook mutation.
- Scheduler/LaunchAgent mutation.
- Source-pointer replacement.
- Owner publication.
- Browser-login/session/credential export.
- External writes.
- Cash movement, PO commitment, supplier contact, ad-platform write, price change, stock change, or owner-decision application.

## Required Work

1. Write a READCHECK file listing every bootstrap file read and the exact accepted boundary.
2. Recheck current protected hashes, DB integrity, lsof holders, SQLite sidecars, and protected git status.
3. If `db/app.db` no longer hashes to `40d21f643caefc38270427096ee615fe0667f7d90b628acf5da56d080ad783d1`, stop `YELLOW` with drift evidence. Do not replay against a new boundary.
4. Copy `db/app.db` into the evidence root and verify the copy hash matches `40d21...`.
5. Run `scripts/recover_order_entries_from_evidence.py --help` and inspect the contract before using it.
6. Run a strict dry-run against the copied DB with:
   - `--db <copied_db>`
   - `--as-of 2026-05-13`
   - `--api-entry-root <Agent794 capture root>`
   - `--output-root <evidence>/dry_run`
   - `--strict`
7. If dry-run is safe, run copied-DB apply only:
   - `ENABLE_ORDER_ENTRY_RECOVERY_WRITE=1`
   - no `ENABLE_ORDER_ENTRY_RECOVERY_PROD_WRITE`
   - `--apply`
   - DB path must be the copied DB, never `db/app.db`.
8. Produce before/after counts for:
   - `fact_order_entries_kaspi`
   - `sales_fact_v2`
   - product-identity warning cohort `23`
   - header-only warning cohort `252`
   - residual header-only or unmapped pairs
9. Rerun focused validators against the copied DB where possible:
   - `validate_order_entries_freshness.py`
   - `validate_operational_stock_integration_gates.py` if it accepts copied DB or safe env routing
   - `validate_order_cashflow_coverage.py`
   - `validate_cashflow_actual_model_separation.py`
   - `validate_exception_queue_db.py`
   - `validate_policy_source_freshness.py`
   - `validate_policy_gate_results.py`
10. Preserve blocker truth. If non-order domains remain blocked, report them as expected. Do not label this combined owner-readiness.

## Closeout Requirements

The closeout must include:

- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`;
- `Domain Status: GREEN/YELLOW/RED`;
- exact copied DB path and SHA;
- before/after table counts;
- validator status table;
- residual blocker list;
- explicit warning-cohort preservation statement;
- non-mutation statement for production DB/workbook/scheduler/external systems.

Gate guidance:

- `GREEN` only if copied-temp replay completed, protected surfaces stayed unchanged, and warning cohorts stayed visible.
- `YELLOW` if replay is blocked by boundary drift or source/validator limitation without forbidden mutation.
- `RED` if protected surfaces were touched, source identity is unsafe, or warning cohorts disappear/productize.
