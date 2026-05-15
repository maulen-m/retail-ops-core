# Agent783 Starter: Stock And Order Source Truth

You are Agent783. Execute only this assigned review-only lane.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/BOUNDARY_REANCHOR_APPROVAL_REVIEW_ONLY_20260512_194357.md`
4. `~/Docs/Autonomous_business/docs/agent_handoffs/ACCEPTED_BOUNDARY_PROOF_WAVE_20260512_194357_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
5. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent777_non_ads_publication_blocker_map_20260512_131702_closeout.md`
6. This starter prompt: `~/Docs/Autonomous_business/docs/agent_handoffs/ACCEPTED_BOUNDARY_PROOF_WAVE_20260512_194357_STARTERS/03_AGENT_783__STOCK_ORDER_SOURCE_TRUTH__PARALLEL_ROOT.md`

## Mission

Map the minimum safe route to make stock and order source truth current for the accepted boundary. Stay local/read-only. Do not fetch from Kaspi/API, import orders, edit workbook, or change stock.

Required first checks:

- Confirm accepted DB and workbook hashes match the re-anchor artifact.
- Confirm DB integrity is `ok`.
- Confirm no DB/workbook holders or SQLite sidecars if your proof reads the live boundary.

Allowed writes:

- assigned evidence folder under `~/Docs/Autonomous_business/exports/validation/accepted_boundary_proof_wave/20260512_194357/agent783_stock_order_source_truth`
- assigned closeout file only

Forbidden:

- Kaspi/API fetch
- order import
- stock mutation
- production DB/workbook mutation
- scheduler restore or mutation
- browser/login automation
- external writes
- owner publication or owner approval request

## Output

Write closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent783_stock_order_source_truth_20260512_194357_closeout.md`

The closeout must include:

- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`
- current stock/order source truth state from local evidence
- exact stale tables/views/gates
- minimum next proof/action route, separated into read-only, copied-temp, and later apply steps
- commands run
- explicit no-write/no-external statement

Gate guidance:

- `GREEN`: source-truth blocker route is fully mapped with no missing local facts.
- `YELLOW`: external/API/live read or owner input is required before the blocker can be removed.
- `RED`: boundary mismatch or unsafe write requirement.
