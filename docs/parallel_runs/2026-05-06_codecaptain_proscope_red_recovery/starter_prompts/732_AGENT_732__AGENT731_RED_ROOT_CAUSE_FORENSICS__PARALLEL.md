# Agent 732 - Agent731 RED Root-Cause Forensics

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_732_agent731_red_root_cause_forensics_closeout.md`

Assigned evidence folder:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_732_evidence/`

Parallel group:

`agent731_red_triage_root`

## Mission

Diagnose why Agent731's fresh owner-request preflight closed RED even though the production boundary was stable.

This is a read-only/root-cause lane. Do not mutate production, do not edit code, do not ask the owner for authorization, do not production-apply, and do not write external systems.

You are not alone in the codebase. Do not revert or overwrite unrelated edits by others.

## Required Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/AGENT731_ORCHESTRATOR_REVIEW_20260508.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_731_fresh_owner_request_preflight_no_apply_closeout.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_731_evidence/`
9. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_70_combined_current_baseline_temp_proof_closeout.md`
10. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_70_evidence/COMMANDS_RUN.md`
11. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_70_evidence/REPLAY_STEP_MATRIX.tsv`
12. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_70_evidence/TABLE_ROWCOUNT_MATRIX.tsv`
13. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_72f_evidence/TEMP_PROOF_SUMMARY.json`
14. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_72f_evidence/temp_proof/snapshot_wrapper_apply_20260504_after_orchestrator_fix/summary.json`
15. `~/Docs/Oracle/Autonomous_business/2026-05-08/213828_AGENT72G_codecaptain_review_pack_after_write_gate_integration/asnwer/Code_Captain_2026-05-08_22_22_00.md`

## Write Boundary

Allowed writes:

- assigned closeout;
- assigned evidence folder;
- read-only analysis tables, diffs, and root-cause notes under assigned evidence.

Forbidden:

- Do not mutate `~/Docs/Autonomous_business/db/app.db`.
- Do not mutate `~/Docs/Autonomous_business/excel_ui/SALES_KSP_CRM_V3.xlsx`.
- Do not mutate code.
- Do not mutate any DB except optional temporary SQLite copies under your evidence folder if you need read-only query convenience.
- Do not mutate schedulers, browser, Web_automation, Kaspi/API, ads, Google, banks, or external systems.
- Do not ask owner authorization.
- Do not production-apply.

## Required Analysis

Produce a root-cause matrix that compares:

- Agent70 GREEN command order and final row counts;
- Agent72F/729 snapshot-wrapper proof assumptions and expected controls;
- Agent731 RED command order, row deltas, negative ledger diagnostic, and leakage matrices.

Answer these questions explicitly:

1. Was Agent731's failure caused by production drift, unsafe holders, or boundary instability?
2. Did Agent731 run a different command order than Agent70's GREEN proof?
3. Did Agent731 use wrapper expectations from an isolated snapshot proof instead of a full-chain proof?
4. Did the snapshot wrapper's `--mode ledger` limitation conflict with Agent70's simulation-based snapshot step?
5. Did missing or late quarantine materialization for `23` and `252` allow product-truth leakage before validators?
6. Are the `17` negative ledger balances new real stock blockers, accepted active-zero candidates, or artifacts of command order/expected baseline?
7. What is the minimum safe next lane: code patch, command-order correction, wrapper extension, temp proof rerun, or CodeCaptain RED pack?

## Required Evidence Files

Create these under the assigned evidence folder:

1. `ROOT_CAUSE_MATRIX.tsv`
2. `COMMAND_ORDER_DIFF.md`
3. `ROW_DELTA_DIFF.tsv`
4. `NEGATIVE_LEDGER_CLASSIFICATION.md`
5. `WARNING_CLASS_VISIBILITY_ANALYSIS.md`
6. `MINIMUM_SAFE_NEXT_LANE.md`

## Closeout

Write a closeout with:

- READCHECK;
- files written;
- commands run;
- root-cause conclusion;
- ranked blockers;
- minimum safe next step;
- explicit mutation statement;
- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.

Gate meanings:

- `GREEN`: root cause is clearly identified and the next lane is executable without owner input.
- `YELLOW`: useful diagnosis, but one decision needs orchestrator/CodeCaptain review.
- `RED`: evidence is inconsistent or there is a discovered production safety issue.
