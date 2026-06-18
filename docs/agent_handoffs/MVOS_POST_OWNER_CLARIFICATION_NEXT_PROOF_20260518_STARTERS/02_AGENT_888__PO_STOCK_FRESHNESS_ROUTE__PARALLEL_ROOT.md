# Agent888: PO Stock Freshness / Production-Readiness Route

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-18_mvos_post_owner_clarification_next_proof_wave/PLAN.md`
4. `~/Docs/Autonomous_business/exports/validation/mvos_owner_clarification_repair_wave/20260518_135603/OWNER_CLARIFICATION_REPAIR_CLOSEOUT.md`
5. `~/Docs/Autonomous_business/exports/validation/mvos_owner_clarification_repair_wave/20260518_135603/po_dashboard_invariants_production_readiness_after_nike_s.stdout.txt`
6. `~/Docs/Autonomous_business/exports/validation/mvos_owner_clarification_repair_wave/20260518_135603/NIKE_SHIRT_S_ORDERABLE_PROOF.json`
7. this assigned starter prompt

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_post_owner_clarification_next_proof_wave/agent888_po_stock_freshness_route_closeout.md`

Assigned evidence folder:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_post_owner_clarification_next_proof_wave/agent888_po_stock_freshness_route_evidence`

## Task

Determine the minimum safe route to move full PO production-readiness from stale-stock blocked to proof-ready.

Produce:

- `PO_STOCK_FRESHNESS_READINESS_MATRIX.json`
- `PO_STOCK_SNAPSHOT_REFRESH_ROUTE.md`
- validator outputs showing the current stale-stock blocker
- any read-only source inventory needed to identify the correct refresh source

## Boundary

Read-only / copied-temp design only.

Do not run production stock refresh apply. Do not mutate `db/app.db`, workbooks, schedulers, source pointers, external systems, stock, PO, cash, prices, or owner-publication surfaces.

If you propose a future production refresh, write the exact proof prerequisites and the exact owner approval phrase that should be required later.

## Gate Guidance

Use `Gate: GREEN` if the route is fully specified and no source ambiguity remains, even if production apply still requires later approval.

Use `Gate: YELLOW` if source truth, CodeCaptain review, or owner approval is required before the route can be trusted.

Use `Gate: RED` if protected-surface drift or unsafe write pressure is detected.
