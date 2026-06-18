# Agent887: C3 Remaining Source Freshness Closure Map

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-18_mvos_post_owner_clarification_next_proof_wave/PLAN.md`
4. `~/Docs/Autonomous_business/exports/validation/mvos_owner_clarification_repair_wave/20260518_135603/OWNER_CLARIFICATION_REPAIR_CLOSEOUT.md`
5. `~/Docs/Autonomous_business/exports/validation/mvos_owner_clarification_repair_wave/20260518_135603/SUCCESSOR_BOARD_AFTER_OWNER_CLARIFICATIONS.md`
6. `~/Docs/Autonomous_business/docs/contracts/mvos_source_contracts/OWNER_QA_PRIORITY_20260518_RETAINED_BLOCKERS.md`
7. this assigned starter prompt

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_post_owner_clarification_next_proof_wave/agent887_c3_remaining_source_freshness_closeout.md`

Assigned evidence folder:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_post_owner_clarification_next_proof_wave/agent887_c3_remaining_source_freshness_evidence`

## Task

Build a read-only map of the remaining C3 source-freshness and policy-gate blockers after the accepted `src_payment_evidence_root` bridge.

Produce:

- `C3_REMAINING_SOURCE_FRESHNESS_BLOCKER_MATRIX.csv`
- `C3_ACCEPTED_PACKET_BRIDGE_CANDIDATES.csv`
- `C3_OWNER_OR_CODECAPTAIN_APPROVAL_NEEDED.md`
- command outputs or JSON/CSV extracts that support the matrix

## Boundary

Read-only only. Do not mutate `db/app.db`, workbooks, schedulers, source pointers, Web_automation, external accounts, ad platforms, cash, PO, stock, prices, or owner-publication surfaces.

You may query SQLite read-only and inspect existing local evidence. If a copied-temp proof is useful, create it only under your assigned evidence folder and state exactly what was copied.

## Gate Guidance

Use `Gate: GREEN` only if the blocker matrix is complete, all remaining blockers are classified, and no production action is needed from your lane.

Use `Gate: YELLOW` if a source or owner/CodeCaptain decision is still required.

Use `Gate: RED` only if the lane cannot safely determine the remaining blockers or finds protected-surface drift.
