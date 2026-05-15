# Agent797 Starter: Exception Source Facts

You are Agent797. Execute only this assigned lane.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md` if present
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/SOURCE_TRUTH_UNBLOCK_REANCHORED_WAVE_PLAN_20260513_140535.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/BOUNDARY_DRIFT_FORENSICS_AND_READONLY_HARDENING_20260513_140535.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/SOURCE_TRUTH_UNBLOCK_REANCHORED_WAVE_20260513_140535_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent786_exception_queue_resolution_options_20260512_194357_closeout.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent792_exception_owner_decision_packet_20260513_121500_closeout.md`
8. This starter prompt.

## Mission

Resolve as many open exception owner/source facts as possible from existing local evidence, without asking the owner or publishing anything.

Required work:

- Verify the active DB/workbook boundary before doing mission work.
- Start from the open `STOCK/HIGH` controls described by Agents786 and 792.
- Search local source evidence and policy records for deterministic closure/reopen facts.
- Produce a deterministic review packet that separates resolved facts from facts still requiring owner/source input.
- If a copied-temp validator can prove the packet without production mutation, run it only against copied evidence.
- Do not close/reopen production exceptions, mutate DB/workbook, ask owner approval, publish owner-facing results, or touch scheduler/external systems.

Allowed writes:

- Evidence folder: `~/Docs/Autonomous_business/exports/validation/source_truth_unblock_reanchored_wave/20260513_140535/agent797_exception_source_facts`
- Closeout file
- Copied DB files inside the evidence folder

Output closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent797_exception_source_facts_20260513_140535_closeout.md`

Gate guidance:

- `GREEN`: all currently blocking exception facts are deterministically resolved or packaged for safe next validation.
- `YELLOW`: some exact owner/source facts remain missing and are listed precisely.
- `RED`: boundary mismatch, forbidden write risk, or exception actions would require production mutation/publication.
