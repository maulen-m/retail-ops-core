# Agent796 Starter: PO Inbound Source Decision

You are Agent796. Execute only this assigned lane.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md` if present
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/SOURCE_TRUTH_UNBLOCK_REANCHORED_WAVE_PLAN_20260513_140535.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/BOUNDARY_DRIFT_FORENSICS_AND_READONLY_HARDENING_20260513_140535.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/SOURCE_TRUTH_UNBLOCK_REANCHORED_WAVE_20260513_140535_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent791_po_inbound_source_decision_20260513_121500_closeout.md`
7. This starter prompt.

## Mission

Resolve the PO inbound fresh-source blocker or produce the smallest exact remaining source requirement.

Required work:

- Verify the active DB/workbook boundary before doing mission work.
- Inspect Agent791's stale-source decision and current PO/inbound source contracts.
- Identify the current canonical inbound source, its as-of timestamp, and exact freshness gap.
- Search for local fresh replacement/source artifacts first.
- If a copied-temp replay or validator can prove a replacement source without production mutation, run it only against copied evidence.
- Do not mutate production DB, workbook, supplier commitments, PO dashboard production surfaces, scheduler, or external systems.

Allowed writes:

- Evidence folder: `~/Docs/Autonomous_business/exports/validation/source_truth_unblock_reanchored_wave/20260513_140535/agent796_po_inbound_source_decision`
- Closeout file
- Copied DB files inside the evidence folder

Output closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent796_po_inbound_source_decision_20260513_140535_closeout.md`

Gate guidance:

- `GREEN`: fresh inbound source or copied-temp proof is ready for the next validation lane.
- `YELLOW`: exact source file, timestamp, owner/source confirmation, or command remains missing.
- `RED`: boundary mismatch, forbidden write risk, or source cannot be safely interpreted.
