# Agent791 Starter: PO Inbound Source Decision

You are Agent791. Execute only this assigned lane.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/protocol/active/PO_making_logic_v3.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/ACCEPTED_BOUNDARY_PROOF_WAVE_RECHECK_20260513_103706.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/TMUX_LIVE_ORCHESTRATOR_PING_POLICY_20260513_121305.md`
6. `~/Docs/Autonomous_business/docs/agent_handoffs/SOURCE_TRUTH_UNBLOCK_WAVE_20260513_121500_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent785_po_inbound_supplier_truth_20260512_194357_closeout.md`
8. This starter prompt.

## Mission

Determine the smallest safe source decision needed to clear `src_inbound_workbook` staleness. Search local evidence for a fresh inbound workbook or accepted replacement source. Do not edit the workbook, contact suppliers, create PO commitments, or mutate DB.

Allowed writes:

- assigned evidence folder: `~/Docs/Autonomous_business/exports/validation/source_truth_unblock_wave/20260513_121500/agent791_po_inbound_source_decision`
- assigned closeout file
- owner/source decision packet only

Output closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent791_po_inbound_source_decision_20260513_121500_closeout.md`

Gate guidance:

- `GREEN`: fresh local inbound source or replacement-source decision packet is complete enough for copied-temp source/gate proof.
- `YELLOW`: owner/source input is required to choose fresh workbook vs replacement source.
- `RED`: boundary mismatch or unsafe write/commitment requirement.
