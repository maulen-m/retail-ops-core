# Agent 58 - Frozen-Baseline Workbook Forensics + WS3 Option B Replay

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_58_frozen_baseline_ws3_replay_closeout.md`

Assigned evidence folder:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_58_evidence/`

Frozen baseline evidence root created by the orchestrator after owner-authorized scheduler pause/restore:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/scheduler_quiet_window_20260506_154459/`

Frozen DB baseline:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/scheduler_quiet_window_20260506_154459/ws3_current_baseline_20260506.db`

Frozen workbook baseline:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/scheduler_quiet_window_20260506_154459/SALES_KSP_CRM_V3.baseline_snapshot.xlsx`

## Mission

Continue WS3 safely from the frozen May 6 baseline captured during the short scheduler quiet window.

First, perform bounded workbook forensics on the frozen workbook tail rows `8053-8137`. Then copy the frozen DB baseline to an Agent58 working temp DB and run the full Agent53 Option B replay sequence on that working copy only.

This is not production apply. This is not Agent54. This lane exists to decide whether WS4 readiness-contract drafting can be launched.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Oracle/Autonomous_business/2026-05-06/120135_TASK-000_codecaptain-proscope-system-review/answer/Code_Captain_2026-05-06_12_32_00_GMT+5.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_57_option_b_current_baseline_temp_proof_closeout.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/scheduler_quiet_window_20260506_154459/copy.log`
9. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/scheduler_quiet_window_20260506_154459/restore.log`
10. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/agent_53_option_b_agent31_production_safe_wrapper_temp_proof_after_52_green_closeout.md`
11. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/agent_53_evidence/replay/commands_run.md`
12. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/agent_53_evidence/validator_exit_summary.tsv`

## Write Boundary

Allowed writes:

- `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_58_frozen_baseline_ws3_replay_closeout.md`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_58_evidence/**`

Allowed DB writes:

- A copied working temp DB under the Agent58 evidence folder only.

Forbidden:

- Do not mutate `~/Docs/Autonomous_business/db/app.db`.
- Do not edit `~/Docs/Autonomous_business/excel_ui/SALES_KSP_CRM_V3.xlsx`.
- Do not edit the frozen baseline DB or frozen baseline workbook in the scheduler quiet-window folder.
- Do not pause or unload schedulers; the orchestrator already restored them for daily shipping.
- Do not write to external repos.
- Do not call live APIs, browser sessions, Kaspi, Meta, bank, Google, or marketing systems.
- Do not ask the owner for the old Agent54 authorization phrase.
- Do not launch Agent54 or draft/authorize production apply.

You are not alone in the codebase. Do not revert unrelated repo edits, including Agent57's validator/test changes.

## Required Sequence

### 1. READCHECK

Write a READCHECK section into the closeout with the files read, assumptions, and exact write boundary.

### 2. Frozen Baseline Verification

Verify and record:

- frozen DB SHA and integrity;
- frozen workbook SHA and dimensions;
- scheduler quiet-window evidence showing no DB lsof during copy and restore completed;
- current live scheduler state is loaded again;
- current live DB/workbook SHA for awareness only.

If the frozen DB integrity fails, stop `RED`.

### 3. Workbook Tail Forensics

Use the frozen workbook baseline, not the moving live workbook, to classify rows `8053-8137`.

Minimum required checks:

- sheet dimensions;
- count nonempty rows in `8053-8137`;
- count unique `№ заказа` values in that tail;
- identify duplicate order IDs inside the tail;
- identify duplicate keys versus prior rows using `№ заказа` + `Артикул` + order-date/order-created-date if available;
- compare tail orders against DB truth in the frozen DB where a stable key exists;
- classify the tail as `PRESERVE`, `REPAIR_REQUIRED`, or `YELLOW_REVIEW_REQUIRED`.

Do not manually repair workbook rows in this lane.

Gate rule:

- If duplicates are exact update/retry artifacts that do not affect downstream truth, document and continue.
- If duplicates imply row-level double-counting risk for sales/stock/cashflow truth, stop `YELLOW` or `RED` before replay unless the replay does not consume the workbook tail.

### 4. Working Temp DB

Copy the frozen DB baseline to:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_58_evidence/agent58_ws3_replay_working.db`

Record source and working DB SHAs before replay.

### 5. Run Focused Validator Regression

Run:

```bash
pytest -q tests/test_policy_registry_c3_contract.py tests/test_policy_materialization_c3.py
```

These should pass with Agent57's validator hardening. If they fail, stop `RED`.

### 6. WS3 Option B Replay

Run the full Agent53 Option B replay sequence on the Agent58 working temp DB only, adapting:

- DB path to `agent58_ws3_replay_working.db`;
- output roots to `agent_58_evidence/replay/**`;
- backup dirs to `agent_58_evidence/replay_backups/**`;
- run IDs to Agent58-specific names;
- expected pre-SHA values to the frozen DB baseline SHA where wrapper commands require exact SHA proof.

Use Agent53's `replay/commands_run.md` as the template. Do not skip validators. If a command is intentionally expected to fail as a known dry-run limitation, document why and match Agent53's accepted behavior.

The target as-of contract remains `2026-05-04`.

Because the frozen DB baseline contains May 6 live intake, explicitly prove or document whether replay steps filter post-as-of data out of the `2026-05-04` decision surface. If post-as-of leakage affects stock/sales/cashflow truth, stop `YELLOW` or `RED`.

### 7. Required Final Temp Gates

On the Agent58 working temp DB, run and record:

```bash
sqlite3 -readonly <temp_db> 'PRAGMA integrity_check;'
python3 scripts/validate_operational_stock_integration_gates.py --db <temp_db>
python3 scripts/validate_policy_source_freshness.py --db <temp_db> --as-of 2026-05-04 --strict --json
python3 scripts/validate_order_cashflow_coverage.py --db <temp_db>
python3 scripts/validate_cashflow_invariants.py --db <temp_db>
python3 scripts/validate_cashflow_actual_model_separation.py --db <temp_db>
python3 scripts/validate_ads_sidecar_readiness.py --db <temp_db>
python3 scripts/validate_ads_offer_universe_coverage.py --db <temp_db>
python3 scripts/validate_ads_spend_reality.py --db <temp_db>
```

Also run any focused wrapper tests relevant to commands you use.

### 8. Production Untouched + Scheduler Restored Proof

At closeout, record:

- live production DB/workbook SHA for awareness;
- live production DB integrity;
- live `lsof db/app.db`;
- live scheduler labels are loaded again;
- git status for `db/app.db` and `excel_ui/SALES_KSP_CRM_V3.xlsx`.

Production may continue to move because schedulers were restored for shipping. That is acceptable for awareness only. Your proof authority is the frozen baseline copy plus Agent58 temp DB.

## Success Criteria

Closeout must include:

- standalone `Gate: GREEN/YELLOW/RED`;
- READCHECK;
- frozen baseline DB/workbook SHAs;
- workbook tail-forensics classification;
- working temp DB path and final SHA;
- replay command/evidence summary;
- validator/gate matrix;
- production untouched proof;
- scheduler-restored proof;
- recommendation: whether WS4 readiness contract can launch from the frozen baseline, or what blocker remains.

## Gate Semantics

`GREEN`:

- workbook tail is safe to preserve or irrelevant to replay truth;
- Agent58 working temp replay passes required gates for `2026-05-04`;
- production DB/workbook are not mutated by this lane;
- scheduler restored proof is present;
- closeout recommends launching WS4 readiness contract.

`YELLOW`:

- workbook tail needs owner/operator review but replay evidence is otherwise useful;
- temp replay is blocked by a specific repairable issue;
- post-as-of leakage risk needs a targeted follow-up.

`RED`:

- frozen DB integrity fails;
- production DB/workbook mutation occurs from this lane;
- replay is unreproducible;
- a required gate fails in a way that hides publication risk;
- scheduler restoration cannot be verified.
