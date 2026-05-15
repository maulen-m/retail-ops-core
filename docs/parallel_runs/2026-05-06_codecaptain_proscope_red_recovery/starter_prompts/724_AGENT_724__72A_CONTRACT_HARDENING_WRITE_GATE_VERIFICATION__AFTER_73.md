# Agent 72A / Launcher 724 - Contract Hardening And Write-Gate Verification

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_72a_contract_hardening_write_gate_verification_closeout.md`

Assigned evidence folder:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_72a_evidence/`

Parallel group:

`agent72a_contract_hardening`

Dependency:

Run only after Agent73 is reviewed and the CodeCaptain Agent72 broad review is ingested.

## Mission

Perform the narrow, non-mutating Agent72A contract-hardening / write-gate verification lane requested by CodeCaptain. Resolve the command/gate gaps in Agent72's production repair/apply contract before any owner-request preflight can open.

This is a verification and specification lane only. Do not production-apply. Do not ask the owner for authorization. Do not mutate the live workbook, schedulers, external systems, or `db/app.db`. Do not implement wrappers or code patches unless a later explicit authorization opens that lane.

You are not alone in the codebase. Do not revert or overwrite unrelated edits by others.

## Required Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/CODECAPTAIN_AGENT72_BROAD_REVIEW_YELLOW_20260508.md`
7. `~/Docs/Oracle/Autonomous_business/2026-05-08/172819_TASK-000_codecaptain-agent72-production-contract-broad-review/ANswer/Code_Captain_2026-05-08_17_48_00.md`
8. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/PRODUCTION_REPAIR_APPLY_CONTRACT_DRAFT_AGENT72_20260508.md`
9. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/AGENT72_ORCHESTRATOR_REVIEW_20260508.md`
10. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/AGENT73_ORCHESTRATOR_REVIEW_20260508.md`
11. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_72_production_repair_apply_contract_draft_closeout.md`
12. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_73_broad_codecaptain_review_pack_closeout.md`

Also inspect, read-only and only as needed:

- `~/Docs/Autonomous_business/docs/WRITE_APPLY_RUNBOOK.md`
- `~/Docs/Autonomous_business/docs/validation/WRITE_SIDE_GATING_CONTRACT.md`
- each script named in Agent72's apply command family;
- relevant tests for those scripts;
- any write-side manifest or schema/gating registry referenced by the repo.

## Write Boundary

Allowed writes:

- `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_72a_contract_hardening_write_gate_verification_closeout.md`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_72a_evidence/**`

Required evidence files:

- `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_72a_evidence/AGENT72A_CONTRACT_PATCH.md`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_72a_evidence/WRITE_GATING_VERIFICATION.tsv`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_72a_evidence/SCRIPT_WRAPPER_DECISION.md`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_72a_evidence/COMMAND_FAMILY_FINALIZATION.md`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_72a_evidence/DRIFT_STABILITY_PREFLIGHT_SPEC.md`

Forbidden:

- Do not mutate `~/Docs/Autonomous_business/db/app.db`.
- Do not mutate `~/Docs/Autonomous_business/excel_ui/SALES_KSP_CRM_V3.xlsx`.
- Do not mutate Agent70, Agent72, or Agent73 evidence.
- Do not mutate scheduler state.
- Do not call live Kaspi/API/bank/Google/Meta/Web_automation/browser/external writes.
- Do not production-apply.
- Do not ask owner for authorization.
- Do not create an owner phrase.
- Do not activate Agent64.
- Do not reuse or request old Agent54.
- Do not hide warning classes or convert header-only rows into product truth.
- Do not implement code patches or wrappers unless a later explicit authorization opens that lane.

## Required Work

1. Write READCHECK into the closeout.
2. Verify CodeCaptain's stricter `YELLOW_NEEDS_SUPPLEMENTAL_PROOF_BEFORE_PREFLIGHT` decision and explain why Agent72A is required before owner-request preflight.
3. Parse Agent72's apply command family and list every script/command that could write production DB truth.
4. For every apply command, produce `WRITE_GATING_VERIFICATION.tsv` with at least:
   - sequence number;
   - script path;
   - command purpose;
   - target table or surface;
   - write type;
   - dry-run default verified: yes/no/unknown;
   - env gate name;
   - env gate verified before first write: yes/no/unknown;
   - explicit `--apply` required: yes/no/unknown;
   - backup behavior;
   - idempotency key / unique constraint / replace-run-id behavior;
   - relevant tests;
   - write-side manifest / registry coverage;
   - decision: production-safe as-is / wrapper required / code patch required / unknown;
   - blocker notes.
5. Produce `AGENT72A_CONTRACT_PATCH.md` resolving all safety placeholders. Runtime variables such as evidence root, run id, backup path, staging DB path, and target pre-SHA may remain runtime-filled for the later preflight. Safety placeholders must not remain unresolved.
6. Produce `SCRIPT_WRAPPER_DECISION.md` specifically deciding:
   - `scripts/rebuild_snapshot.py`;
   - `scripts/materialize_storeb_product_identity_quarantine.py`;
   - `scripts/materialize_header_only_source_gap_quarantine.py`.
7. Produce `COMMAND_FAMILY_FINALIZATION.md` with the final exact command-family shape for the later staging replay and production apply. It must include no ad hoc SQL, no implicit migration during validators, no workbook mutation, no scheduler mutation, and no external writes.
8. Produce `DRIFT_STABILITY_PREFLIGHT_SPEC.md` defining the later preflight stability proof:
   - DB SHA at start;
   - DB SHA immediately before owner-request packet is considered;
   - workbook SHA at both points;
   - DB integrity;
   - lsof and sidecar checks;
   - protected git status;
   - scheduler/holder status;
   - rule: any unexplained DB SHA drift closes the lane RED.
9. If a wrapper or code patch is required, do not implement it. Specify the exact next lane required.
10. Run only read-only/static checks and docs lint if safe.
11. Write closeout with standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.

## Gate Semantics

`GREEN`:

- All safety placeholders are resolved into reviewed concepts or later-runtime variables.
- Every apply command has verified dry-run default, env gate, explicit `--apply`, backup/idempotency story, and manifest/registry/test evidence.
- Wrapper decisions are clear and no wrapper/code patch is required before owner-request preflight.
- Drift-stability preflight spec is complete.
- No forbidden mutation occurred.

`YELLOW`:

- Contract is mostly hardenable but one or more commands require wrapper/code patch, missing manifest coverage, missing tests, unknown env gate behavior, or additional static proof.
- No forbidden mutation occurred.

`RED`:

- Any command is unsafe by design for production, any forbidden mutation occurs, owner authorization wording is generated/requested, old Agent54/Agent64 is activated, warning classes are hidden/productized, or the lane cannot determine the command family safely.
