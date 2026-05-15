# Agent 750 - Option C Validate-Only Plan After Current dec77 Re-Anchor

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_750_option_c_validate_only_plan_after_747_748_749_closeout.md`

Assigned evidence folder:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_750_option_c_validate_only_plan_after_747_748_749_evidence/`

Parallel group:

`after_747_748_749`

Dependencies:

- Agent747 closeout reviewed non-RED: current `dec77` release anchor is `YELLOW`.
- Agent748 closeout reviewed non-RED: current `dec77` independent confirmation is `YELLOW`.
- Agent749 closeout reviewed `GREEN`: strict daily preflight proof-window lock hardening landed.
- Orchestrator explicitly launches this starter after reviewing all three closeouts.

## Mission

Draft the current-boundary Option C validate-only implementation plan and starter-pack skeleton. Use the current production DB boundary, not the stale Agent742 `9c51...ee53` boundary.

Option C validate-only means the daily system can be designed and dry-run with copied DB/read-only outputs, trust banners, exception queues, owner brief drafts, and proof-window controls, but true production scheduler/write authority remains blocked.

Do not implement scheduler automation. Do not mutate production DB/workbook. Do not write external systems.

## Required Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/CODECAPTAIN_POST_AGENT742_OPTION_C_PREPROD_REVIEW_20260509.md`
7. `~/Docs/Oracle/Autonomous_business/2026-05-09/192420_TASK-000_codecaptain-option-c-preprod-review-after-agent742/answer/Code_Captain_09.05.2026_20_38_06.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_746_orchestrator_db_drift_forensics_closeout.md`
9. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_747_current_dec77_release_anchor_closeout.md`
10. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_748_current_dec77_independent_confirmation_closeout.md`
11. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_749_scheduler_proof_window_hardening_closeout.md`
12. `~/Docs/Autonomous_business/exports/validation/db_only_repair_release/2026-05-09_current_dec77_reanchor/CURRENT_DEC77_RELEASE_ANCHOR.md`

## Current Boundary To Use

- Production DB: `~/Docs/Autonomous_business/db/app.db`
- Current DB SHA: `dec77f37cc63147e54e9085a6a0f9564d9ead9e57aea0d8483dc0473886bee64`
- Protected workbook SHA: `3ad4b81c39b125c48b34c02afb8a30eafd348658e07afd27c11f628b8987025c`
- Current release-anchor folder: `~/Docs/Autonomous_business/exports/validation/db_only_repair_release/2026-05-09_current_dec77_reanchor/`
- Proof-window lock hardening: `scripts/run_strict_daily_preflight.py` supports `AB_PROOF_WINDOW_LOCK_PATH` and default `config/proof_window.lock`; locked preflight exits `75` with `STRICT_DAILY_PREFLIGHT_BLOCKED_BY_PROOF_WINDOW_LOCK`.

## Write Boundary

Allowed writes:

- assigned closeout;
- assigned evidence folder;
- current-boundary validate-only plan document under:
  `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/OPTION_C_VALIDATE_ONLY_IMPLEMENTATION_PLAN_AFTER_DEC77_REANCHOR_20260509.md`
- optional starter prompt drafts under:
  `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/starter_prompts/`
  but only for validate-only/read-only/copy-DB lanes.

Forbidden:

- Do not mutate `~/Docs/Autonomous_business/db/app.db`.
- Do not mutate `~/Docs/Autonomous_business/excel_ui/SALES_KSP_CRM_V3.xlsx`.
- Do not mutate schedulers or LaunchAgents.
- Do not install, enable, or modify launchd/plist automation.
- Do not create or remove the real `config/proof_window.lock`; describe its use only.
- Do not write to external systems, Kaspi/API, ads platforms, Google, banks, browser automation, Web_automation, or external repos.
- Do not claim owner PnL/cash/PO/ad decisions are production GREEN.
- Do not ask owner for approval.
- Do not reuse old Agent54 phrase or activate Agent64.

## Required Plan Content

The plan must include:

1. Current `dec77` release-anchor dependency and DB/workbook SHA boundary.
2. Why Agent743/744 and stale Agent745 are superseded and must not be used as current boundary authority.
3. Option C validate-only daily workflow from source freshness to owner brief draft.
4. Data inputs and freshness gates:
   - orders/status;
   - sales/order entries;
   - stock ledger/snapshot;
   - ads;
   - cashflow;
   - PO/inbound/cargo/supplier obligations;
   - exception queues;
   - owner outputs.
5. First owner-output surface recommendation. Prefer `Cash Risk Daily` first unless evidence shows another order is safer.
6. Trust banner schema:
   - what is GREEN;
   - what is WARNING;
   - what is BLOCKED;
   - which owner decisions are allowed or blocked.
7. Validate-only runner design:
   - copied DB or read-only mode;
   - proof-window lock usage;
   - no scheduler install;
   - no external writes;
   - no workbook writes;
   - deterministic evidence folder;
   - validator matrix.
8. Tests and validators required before any future production scheduler lane.
9. Stoplines before scheduler/write authority.
10. Proposed next helper-agent wave, with one write-capable agent maximum and analysts read-only.
11. Explicit human approvals required later.
12. Whether CodeCaptain review is required before implementing validate-only code, and what pack should be sent if required.

## Gate Semantics

`GREEN`:

- clear validate-only plan;
- no production automation scope creep;
- Agent747/748/749 dependencies are correctly used as the current boundary;
- stale Agent742/743/744/745 authority is explicitly superseded where appropriate;
- owner decision surfaces and trust banners are concrete;
- next helper-agent wave is safe and dependency-gated.

`YELLOW`:

- plan is mostly usable but needs orchestrator/owner/CodeCaptain clarification before launching implementation.

`RED`:

- plan implies scheduler/external/workbook/production writes without authorization;
- plan hides warning cohorts or treats Option C as production-authorized;
- dependencies were not actually reviewed.

## Closeout

Write closeout with READCHECK, files written, plan path, remaining stoplines, recommended launch sequence, CodeCaptain-review recommendation, and standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.
