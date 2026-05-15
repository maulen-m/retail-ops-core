# Agent 733 - Agent731 RED Temp-Only Variant Proof

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_733_agent731_red_temp_variant_proof_closeout.md`

Assigned evidence folder:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_733_evidence/`

Parallel group:

`agent731_red_triage_root`

## Mission

Run controlled temp-only replay variants to identify the minimum command-family correction after Agent731 RED.

This lane may create and mutate SQLite copies only under the assigned evidence folder. It must not mutate production DB, workbook, code, schedulers, browser, Web_automation, Kaspi/API, ads, Google, banks, or external systems.

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
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_731_evidence/backups/app_pre_agent731_20260508_223146.db`
9. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_70_evidence/COMMANDS_RUN.md`
10. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_70_evidence/REPLAY_STEP_MATRIX.tsv`
11. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_72f_evidence/temp_proof/snapshot_wrapper_apply_20260504_after_orchestrator_fix/summary.json`

## Write Boundary

Allowed writes:

- assigned closeout;
- assigned evidence folder;
- SQLite DB copies under assigned evidence only;
- logs, matrices, and summaries under assigned evidence only.

Forbidden:

- Do not mutate `~/Docs/Autonomous_business/db/app.db`.
- Do not mutate `~/Docs/Autonomous_business/excel_ui/SALES_KSP_CRM_V3.xlsx`.
- Do not mutate code.
- Do not write outside assigned evidence, except harmless command stdout/stderr redirected into assigned evidence.
- Do not production-apply.
- Do not ask owner authorization.
- Do not run external-system writes.

If a diagnostic script unexpectedly emits a file outside the assigned evidence folder, do not continue silently. Copy the diagnostic into evidence, record the source path, stat, SHA if available, and command that emitted it, remove the out-of-bound diagnostic if it is an untracked generated diagnostic, then continue only if protected production surfaces remain unchanged. If unsure, close RED.

## Required Temp Variants

Use the Agent731 production backup as the starting DB for fresh copies:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_731_evidence/backups/app_pre_agent731_20260508_223146.db`

Variant A: reproduce Agent731 failing sequence on a clean copy and record exact counts/negative classes.

Variant B: run the Agent70 GREEN sequence as closely as possible on a fresh copy, with all writes targeting the copy only. Use direct scripts only because the target is an evidence copy, and label this as non-production-proof if any command would be unsafe for production.

Variant C: test snapshot wrapper isolation on a fresh copy using Agent72F expected controls, to confirm whether the wrapper still passes before sales/ledger replay.

Variant D: if safe and time allows, test snapshot wrapper after applying quarantine steps before snapshot, or prove why that sequence is impossible without code changes.

For each variant, record:

- start SHA;
- commands;
- exit codes;
- row counts for key tables;
- negative ledger count;
- final validator statuses;
- leakage/cash preservation status if applicable;
- whether the variant can be a production-safe command contract or only a diagnostic.

## Required Evidence Files

Create these under assigned evidence:

1. `VARIANT_MATRIX.tsv`
2. `COMMANDS_RUN.md`
3. `ROWCOUNT_MATRIX.tsv`
4. `NEGATIVE_LEDGER_MATRIX.tsv`
5. `VALIDATOR_MATRIX.tsv`
6. `LEAKAGE_AND_CASH_MATRIX.tsv`
7. `RECOMMENDED_CORRECTED_SEQUENCE.md`

## Gate Semantics

`GREEN`:

- variants clearly identify a corrected temp-only sequence or prove a specific code/wrapper patch is required;
- no production/workbook/code/external mutation occurred.

`YELLOW`:

- useful variant evidence exists, but the corrected sequence needs orchestrator/CodeCaptain choice.

`RED`:

- evidence is inconsistent, production was touched, or no safe diagnostic conclusion can be made.

## Closeout

Write a closeout with READCHECK, files written, commands run, variant results, mutation statement, recommended next step, and standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.
