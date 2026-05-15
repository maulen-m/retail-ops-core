# Agent789 Starter: Stock And Order Source Evidence

You are Agent789. Execute only this assigned lane.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/ACCEPTED_BOUNDARY_PROOF_WAVE_RECHECK_20260513_103706.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/TMUX_LIVE_ORCHESTRATOR_PING_POLICY_20260513_121305.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/SOURCE_TRUTH_UNBLOCK_WAVE_20260513_121500_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent783_stock_order_source_truth_20260512_194357_closeout.md`
7. This starter prompt.

## Mission

Find whether accepted local identity-bearing order-entry evidence exists for `2026-05-05..2026-05-11`. If sufficient local evidence exists, prove the copied-temp stock/order replay route on a copied DB. If it does not exist, produce the exact external/API read/import approval request needed.

Forbidden:

- live Kaspi/API fetch
- order import into production
- stock mutation
- production DB/workbook mutation
- scheduler restore or mutation
- external writes
- browser/login automation
- owner publication or owner approval request

Allowed writes:

- assigned evidence folder: `~/Docs/Autonomous_business/exports/validation/source_truth_unblock_wave/20260513_121500/agent789_stock_order_source_evidence`
- assigned closeout file
- copied DB files only if local source evidence is sufficient for copy-only replay

Output closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent789_stock_order_source_evidence_20260513_121500_closeout.md`

Gate guidance:

- `GREEN`: local source evidence is sufficient and copied-temp replay proof reaches a clear stock/order route.
- `YELLOW`: source evidence is missing and a bounded external/API read/import approval request is required.
- `RED`: boundary mismatch or unsafe write requirement.
