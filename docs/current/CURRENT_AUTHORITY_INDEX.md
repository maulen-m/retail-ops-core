# CURRENT_AUTHORITY_INDEX

Status: ACTIVE_PHASE46_OWNER_ACTION_UNBLOCK_PACKET
Created: 2026-05-21
Last aligned: 2026-05-22 Phase 46 owner action unblock packet
Scope: `~/Docs/Autonomous_business`

This file is a routing index. It does not authorize production DB writes, workbook writes, scheduler changes, source-pointer writes, external writes, cash movement, PO commitment, stock changes, price changes, owner publication, production preflight, or production apply.

## Current Decision

Current authority is the Phase42 CodeCaptain review pack plus the Phase45
runway/restart addendum, the Phase46 owner-action unblock packet, and the
canonical `docs/current` blocker/source maps.
Phase 0's Agent B/C routing conflict and older Phase 18/19/20/21/22/25/26
review packets are no longer the active decision point.

- Current overall gate: `YELLOW`.
- Accepted local movement is copied-temp/read-only evidence and documentation
  alignment only.
- Copied-temp closures do not authorize production truth, production preflight,
  production apply, owner publication, scheduler resume, source-pointer writes,
  workbook writes, or external mutations.
- The base active review surface is
  `~/Docs/Oracle/Autonomous_business/2026-05-22/062954_TASK-000_mvos-phase42-codecaptain-review-pack-refresh`.
- The current addendum review surface is
  `docs/parallel_runs/2026-05-22_mvos_phase45_codecaptain_runway_addendum/CODECAPTAIN_PHASE45_RUNWAY_ADDENDUM_PROMPT.md`.
- The current owner-action surface is
  `docs/parallel_runs/2026-05-22_mvos_phase46_owner_action_unblock_packet/PHASE46_OWNER_ACTION_UNBLOCK_PACKET.md`.
- Retained blockers remain literal: physical stock source truth, C3 source
  freshness/policy gates, STOREB/ACMEWEAR ads truth, current-window status-ledger
  continuity, PO money through physical-stock drift, B012 `LINE-31-LS` COGS
  authority/default-route proof, dirty repo readiness, and automation pause
  boundary.

## Active Execution Authority

| role | active authority | status | notes |
| --- | --- | --- | --- |
| Current execution plan | `docs/current/FINAL_10_OUT_OF_10_EXECUTION_PLAN.md` | ACTIVE | Supersedes scattered `PLAN*.md` files for current routing. |
| Current blocker board | `docs/current/CURRENT_BLOCKER_BOARD.tsv` | ACTIVE_ROUTE | Current retained blockers, copied-temp closures, owner questions, and exit gates. |
| Current source truth map | `docs/current/CURRENT_SOURCE_TRUTH_MAP.md` | ACTIVE_ROUTE | Current source-freshness/source-authority routing; not production truth by itself. |
| Phase 20 owner facts addendum | `docs/contracts/mvos_source_contracts/PHASE20_OWNER_FACTS_RETAINED_BLOCKER_ADDENDUM_20260522.md` | ACTIVE_NON_PRODUCTION_ADDENDUM | Canonicalizes owner-confirmed Universal identity, no-fresher-physical-stock fact, copied-temp closures, and retained blocker wording. |
| Phase 42 CodeCaptain review packet | `~/Docs/Oracle/Autonomous_business/2026-05-22/062954_TASK-000_mvos-phase42-codecaptain-review-pack-refresh` | REVIEW_BASE_CURRENT | Base review pack; does not authorize production preflight/apply. |
| Phase 45 runway addendum | `docs/parallel_runs/2026-05-22_mvos_phase45_codecaptain_runway_addendum/CODECAPTAIN_PHASE45_RUNWAY_ADDENDUM_PROMPT.md` | REVIEW_ADDENDUM_CURRENT | Small addendum for disk/runroot stopline and next copied-temp launch contract. |
| Phase 46 owner-action unblock packet | `docs/parallel_runs/2026-05-22_mvos_phase46_owner_action_unblock_packet/PHASE46_OWNER_ACTION_UNBLOCK_PACKET.md` | OWNER_ACTION_CURRENT | Exact cleanup phrase, cleanup command, run-root alternative, and copied DB helper command for the next unblock step. |
| 10/10 acceptance target | `docs/contracts/MVOS_10_OUT_OF_10_DECISION_GRADE_ACCEPTANCE_CONTRACT.md` | CANDIDATE_PENDING_OWNER_APPROVAL | Implementation target only until owner approves final target wording. |
| Source contract registry | `docs/contracts/mvos_source_contracts/ACTIVE_MVOS_SOURCE_CONTRACT_REGISTRY.json` | ACTIVE_ROUTE | Registers source substitutions, exclusions, retained blockers, and copied-temp contracts. |
| Repo contract | `AGENTS.md` | ACTIVE | Defines repo boundary, write safety, required gates, and stoplines. |
| Docs router | `docs/00_START_HERE.md` | ACTIVE | Routes agents to owning docs by task type. |
| Operating protocol | `.claude/OPERATING.md` | ACTIVE_MUTABLE_WORKFLOW | Workflow and evidence routing only, not formula authority. |

## Rule And Formula Authority

These files own business rules, formulas, schema semantics, and UI/input contracts. Current docs must route to them rather than duplicate or silently override them.

| domain | authority |
| --- | --- |
| Inventory math | `docs/inventory/Master_Inventory_Rules_v9.md` |
| PO and size allocation | `docs/protocol/active/PO_making_logic_v3.md` |
| Sales and data model | `docs/inventory/Sales_Data_Model_V16.md` |
| Excel UI/input contract | `docs/inventory/Excel_UI_Contract_for_CRM_V1.md` |
| Repo architecture | `ARCHITECTURE.md` |
| Daily ops | `docs/DAILY_SOP.md` |
| Cashflow | `docs/KASPI_ORDER_CASHFLOW_TRACKING.md` and `config/payout_model.yaml` |

## Write And Automation Authority

| surface | authority | current status |
| --- | --- | --- |
| Write-side gating | `docs/WRITE_SIDE_GATING_CONTRACT.md` and `config/write_side_gating_manifest.yaml` | Fail-closed: env gate plus `--apply` required for writes. |
| Write apply runbook | `docs/WRITE_APPLY_RUNBOOK.md` | Backup-first, exact apply command, rollback evidence required. |
| Parallel execution | `docs/PARALLEL_EXECUTION_PROTOCOL.md` | One write-capable execution agent; read-only analysts publish to handoff folders. |
| Automation pause/resume | `docs/ops/BUSINESS_AUTOMATION_CONTROL_RUNBOOK.md`, `config/business_automation_manifest.json`, `scripts/manage_business_automation.py` | Current evidence says all-business automation is paused. Resume needs exact owner scope. |

## Non-Authority Surfaces

| surface | classification | allowed use |
| --- | --- | --- |
| `.claude/*` | Mutable work state | Progress, issues, decisions, session log. Not business-rule authority. |
| `exports/` | Derived evidence/output | Evidence and dashboards only. Not source of formulas. |
| Workbooks | UI/input/reference | Not silent business-rule authority. Mutations require explicit workbook authority. |
| Old `PLAN*.md` files | Historical plans | Indexed in `SUPERSEDED_PLAN_INDEX.tsv`; not current execution authority. |
| Copied-temp proof | Non-production proof | Can support review/preflight discussion only. Never production truth by itself. |

## Open Owner Authority Items

| request_id | owner decision needed | default until answered |
| --- | --- | --- |
| H001 | Approve or amend final 10/10 target wording. | Use candidate contract for implementation only; no final owner-publication claim. |
| H002 | Provide or authorize fresh independent physical stock source, or request a CodeCaptain-reviewed substitute stock/capital-risk contract. Owner confirmed no fresher physical stock source currently exists. | Keep PO/SKU, stock actions, PO money, and stock-dependent publication blocked. |
| H003 | Approve exact automation labels/groups to resume when live ops require it. | Keep all-business automation paused. |
| H004 | Universal offer `132822924_328581041` identity is owner-confirmed for copied-temp proof planning only. | Treat copied-temp `CL_NEW-CLO_MEN_LEG_WHITE_XL` mapping as review evidence only; keep production/source application blocked until review/preflight authority. |
| H005 | Provide exact production apply phrase later after reviewed preflight. | No production apply. |
| H006 | Provide explicit copied-temp-only `LINE-31-LS` COGS authority, accept a component-level ChildSum route, or leave `ACMEWEAR 929183530 / LINE-31-LS_2XL` quarantined for CodeCaptain review. | Keep B012 repeated-run/daily-autonomy gate `YELLOW`; do not infer LINE-31-LS cost from adjacent families. |
| H007 | Provide same-window status-ledger source through `2026-05-18`, or request a scoped status-ledger contract review. | Keep current-window lifecycle/status publication blocked; copied-temp day-complete closure remains non-production evidence only. |
