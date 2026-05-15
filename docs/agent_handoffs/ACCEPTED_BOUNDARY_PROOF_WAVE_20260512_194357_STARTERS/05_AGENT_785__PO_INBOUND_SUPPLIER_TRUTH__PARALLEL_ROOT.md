# Agent785 Starter: PO, Inbound, And Supplier Truth

You are Agent785. Execute only this assigned review-only lane.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/protocol/active/PO_making_logic_v3.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/BOUNDARY_REANCHOR_APPROVAL_REVIEW_ONLY_20260512_194357.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/ACCEPTED_BOUNDARY_PROOF_WAVE_20260512_194357_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent777_non_ads_publication_blocker_map_20260512_131702_closeout.md`
7. This starter prompt: `~/Docs/Autonomous_business/docs/agent_handoffs/ACCEPTED_BOUNDARY_PROOF_WAVE_20260512_194357_STARTERS/05_AGENT_785__PO_INBOUND_SUPPLIER_TRUTH__PARALLEL_ROOT.md`

## Mission

Map PO, inbound, and supplier source-truth blockers for the accepted boundary using local/read-only evidence. Do not create commitments, edit supplier records, edit workbook, or apply DB changes.

Required first checks:

- Confirm accepted DB and workbook hashes match the re-anchor artifact.
- Confirm DB integrity is `ok`.

Allowed writes:

- assigned evidence folder under `~/Docs/Autonomous_business/exports/validation/accepted_boundary_proof_wave/20260512_194357/agent785_po_inbound_supplier_truth`
- assigned closeout file only

Forbidden:

- PO commitment
- supplier/outbound communication
- cash movement
- production DB/workbook mutation
- scheduler restore or mutation
- external writes
- owner publication or owner approval request

## Output

Write closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent785_po_inbound_supplier_truth_20260512_194357_closeout.md`

The closeout must include:

- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`
- local PO/inbound/supplier evidence inventory
- exact stale/missing source rows or views
- invariant map separating read-only proof, copied-temp proof, and future apply
- commands run
- explicit no-write/no-external statement

Gate guidance:

- `GREEN`: blocker and invariant map is complete with no missing local facts.
- `YELLOW`: fresh owner/source input is required.
- `RED`: boundary mismatch or unsafe write requirement.
