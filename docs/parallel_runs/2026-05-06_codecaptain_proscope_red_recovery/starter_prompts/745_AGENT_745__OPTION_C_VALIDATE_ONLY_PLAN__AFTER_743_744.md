# Agent 745 - Option C Validate-Only Plan After Release Anchor

Status: SUPERSEDED_DO_NOT_LAUNCH

This starter is historical only. It depends on Agent743/744 and the superseded Agent742 `9c51...ee53` boundary. For current `dec77...ee64` Option C validate-only planning, use:

`~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/starter_prompts/750_AGENT_750__OPTION_C_VALIDATE_ONLY_PLAN__AFTER_747_748_749.md`

Do not launch this Agent745 starter unless a later dated handoff explicitly reactivates it.

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_745_option_c_validate_only_plan_closeout.md`

Assigned evidence folder:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_745_option_c_validate_only_plan_evidence/`

Parallel group:

`after_743_744`

Dependencies:

- Agent743 closeout reviewed non-RED.
- Agent744 closeout reviewed non-RED.
- Orchestrator explicitly launches this starter after reviewing both closeouts.

## Mission

Draft the Option C validate-only implementation plan and starter-pack skeleton. Do not implement scheduler automation. Do not mutate production DB/workbook. Do not write external systems.

Option C validate-only means the daily system can be designed and dry-run with copied DB/read-only outputs, trust banners, exception queues, and owner brief drafts, but true production scheduler/write authority remains blocked.

## Required Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/CODECAPTAIN_POST_AGENT742_OPTION_C_PREPROD_REVIEW_20260509.md`
7. `~/Docs/Oracle/Autonomous_business/2026-05-09/192420_TASK-000_codecaptain-option-c-preprod-review-after-agent742/answer/Code_Captain_09.05.2026_20_38_06.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_743_post_agent742_release_anchor_closeout.md`
9. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_744_independent_post_apply_confirmation_closeout.md`

## Write Boundary

Allowed writes:

- assigned closeout;
- assigned evidence folder;
- validate-only plan document under:
  `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/OPTION_C_VALIDATE_ONLY_IMPLEMENTATION_PLAN_AFTER_AGENT742_20260509.md`
- optional starter prompt drafts under:
  `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/starter_prompts/`
  but only for validate-only/read-only/copy-DB lanes.

Forbidden:

- Do not mutate `~/Docs/Autonomous_business/db/app.db`.
- Do not mutate `~/Docs/Autonomous_business/excel_ui/SALES_KSP_CRM_V3.xlsx`.
- Do not mutate schedulers.
- Do not install, enable, or modify launchd/plist automation.
- Do not write to external systems, Kaspi/API, ads platforms, Google, banks, browser automation, Web_automation, or external repos.
- Do not claim owner PnL/cash/PO/ad decisions are production GREEN.
- Do not ask owner for approval.

## Required Plan Content

The plan must include:

1. Release-anchor dependency and current DB/workbook SHA boundary.
2. Option C validate-only daily workflow.
3. Data inputs and freshness gates:
   - orders/status;
   - sales/order entries;
   - stock ledger/snapshot;
   - ads;
   - cashflow;
   - PO/inbound/cargo/supplier obligations;
   - exception queues;
   - owner outputs.
4. First owner-output surface recommendation. Prefer `Cash Risk Daily` first unless evidence shows another order is safer.
5. Trust banner schema:
   - what is GREEN;
   - what is WARNING;
   - what is BLOCKED;
   - which owner decisions are allowed or blocked.
6. Validate-only runner design:
   - copied DB or read-only mode;
   - no scheduler install;
   - no external writes;
   - no workbook writes;
   - deterministic evidence folder;
   - validator matrix.
7. Tests and validators required before any future production scheduler lane.
8. Stoplines before scheduler/write authority.
9. Proposed next helper-agent wave, with one write-capable agent maximum and analysts read-only.
10. Explicit human approvals required later.

## Gate Semantics

`GREEN`:

- clear validate-only plan;
- no production automation scope creep;
- release anchor and independent confirmation are correctly used as dependencies;
- owner decision surfaces and trust banners are concrete;
- next helper-agent wave is safe and dependency-gated.

`YELLOW`:

- plan is mostly usable but needs orchestrator/owner clarification before launching.

`RED`:

- plan implies scheduler/external/workbook/production writes without authorization;
- plan hides warning cohorts or treats Option C as production-authorized;
- dependencies were not actually reviewed.

## Closeout

Write closeout with READCHECK, files written, plan path, remaining stoplines, recommended launch sequence, and standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.
