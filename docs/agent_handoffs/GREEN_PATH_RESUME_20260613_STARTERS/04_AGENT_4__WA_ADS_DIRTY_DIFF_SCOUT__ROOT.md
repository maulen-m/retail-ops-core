# Agent 4 - WA Ads And Dirty Diff Scout

Assigned closeout:
`~/Docs/Autonomous_business_agent_handoffs/2026-06-13_green_path_resume/agent_4_wa_ads_dirty_diff_scout_closeout.md`

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Web_automation/AGENTS.md` if present
3. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/handoff/ORCHESTRATOR_HANDOFF.md`
4. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/GREEN_PATH_RESUME_ADDENDUM_20260613.md`
5. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/starter_pack/03_packets_phase2.md`
6. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/starter_pack/04_packets_phase3_4_5.md`

Role: read-only scout for WA/ads readiness and dirty-diff classification. You may write only your assigned closeout file.

Tasks:

- Confirm WA branch and dirty state were preserved in `~/Backups/green_path/20260613_1855_resume_preserve`.
- Re-baseline ads watcher/canonical freshness read-only.
- Identify any WA dirty files that overlap Phase 2 or Phase 3 green-path lanes.
- Confirm no Meta/Instagram ads surface is in scope; Kaspi only.
- Do not run browser login automation. Do not mutate WA, AB, DBs, LaunchAgents, workbooks, prices, ads, or external systems.

Closeout requirements:

- Standalone line `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.
- Include overlap classification: safe/needs serialization/blocks.
- Use `Gate: YELLOW` if dirty overlap needs orchestration sequencing.
- Use `Gate: RED` only if WA/ads state makes the first AB `PKT-LINES` writer unsafe.
