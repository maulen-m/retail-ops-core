# Green Path Resume Addendum - 2026-06-13

Status: active resume contract for Phase 2 execution.

This addendum does not replace the green-path handoff. It tightens the resume boundary after the 2026-06-13 waybill incident and the owner-approved daily automation window.

## Current Baseline

- Canonical handoff: `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/handoff/ORCHESTRATOR_HANDOFF.md`
- Emergency waybill repair closeout: `~/Docs/Autonomous_business/exports/validation/waybill_telegram_delivery_alignment_repair_20260613/closeout.md`
- Daily ops state at resume: paused, `daily-ops loaded=0/10`
- Waybill batch state at resume: 29 API shipment-ready orders, 21 grouped PDFs, Telegram confirmed 21/21
- Phase state at resume: Phase -1/0/1 complete, no governed Phase-2 DB write recorded
- Private preservation pack: `~/Backups/green_path/20260613_1855_resume_preserve`
- Active branches:
  - AB: `greenpath/20260613-phase2-truth`
  - WA: `greenpath/20260613-phase2-truth`

## Resume Corrections

- Treat the waybill repair as part of the new baseline. Any scheduler reinstall must re-verify that the waybill Telegram path uses the dedicated waybill pair and does not inject generic Telegram env keys.
- Use the daily automation window as a hard operating boundary: 20:00 to 14:00 Asia/Almaty is available for paused automation work; 14:00 to 20:00 is protected for daily order operations unless the owner explicitly says otherwise.
- Keep daily ops paused during Phase-2 writes. Resume only through `scripts/manage_business_automation.py` with dry-run, `ENABLE_BUSINESS_AUTOMATION_CONTROL=1 --apply`, evidence, and verify.
- Preserve dirty work before applying. Do not flatten AB/WA dirty state into a broad commit; commit only curated green-path changes by lane.
- Tighten the Phase-2 sequence: `PKT-FX` must be green before any `PKT-PROFIT` apply that depends on FX or COGS authority. A known-COGS backfill may proceed earlier only if the dry-run proves it does not depend on FX.

## Orchestration Contract

- Use fresh tmux panes in the `autonomous_business` session and deterministic hybrid / receiver or monitor-only routing.
- Root wave is read-only except for closeout files under `~/Docs/Autonomous_business_agent_handoffs/2026-06-13_green_path_resume/`.
- The first writer lane is `PKT-LINES`, and it must not start until root closeouts are reviewed by the orchestrator.
- Exactly one write-capable agent may hold the AB write lease at a time.
- Every closeout must contain a standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED` line.
- File closeouts and validation evidence are authoritative; pane pings are wake-up hints only.

## Owner Contact Policy

No new owner approval phrase is required for Phase 2 if `OWNER_DECISIONS_RECORDED.yaml` remains binding.

The only allowed owner contact before acceptance is STOP-THE-LINE:

- backup or restore failure
- data loss evidence
- secret exposure
- unexpected write-diff rows with no policy coverage that block more than 50% of remaining work
- any live external action outside an approved envelope

Everything else must be applied if covered by policy, or parked in `DEFERRED_QUEUE.md` with exposure and resurface point.
