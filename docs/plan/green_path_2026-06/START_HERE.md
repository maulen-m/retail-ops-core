# START HERE — Green-Path program (fresh orchestrator)

You are resuming a mid-execution program to bring the Autonomous_business + Web_automation Kaspi operation to a defined 100%-green state. **Status: PAUSED at the Phase-1 → Phase-2 boundary** (Phase -1/0/1 done; no governed Phase-2 DB write yet).

**Read in this order:**
1. `handoff/ORCHESTRATOR_HANDOFF.md` ← the complete handoff (read top-to-bottom; §0 = first 5 actions, §7 = exact next steps, appendices = verified system state).
2. `OWNER_DECISIONS_RECORDED.yaml` ← the binding decisions (consume this; never the pack prose).
3. `MASTER_REMEDIATION_PLAN.md` ← operating rules + workstreams + rollback map.
4. `green_path_run/scoreboard.csv` + `green_path_run/STATUS.md` ← exactly where it stands.
5. `starter_pack/03_packets_phase2.md` ← your next dispatch packets.
6. `dashboard/DASHBOARD_UPKEEP.md` ← the LIVE progress dashboard you are required to keep current.

**Then act:** §7 of the handoff — first lane is PKT-LINES (entries backfill). You are the single write-capable orchestrator; backup-first, single-lease, STOP-THE-LINE is the only owner ping, Kaspi-ads-only.

**Keep the live dashboard current (mandatory):** open `dashboard/dashboard.html` in a browser (it auto-refreshes ~15s). Whenever you update `green_path_run/scoreboard.csv` / `STATUS.md`, mirror it in `dashboard/progress-data.js` — flip the gate `status`, bump `updated`, push an `activity` line; edit only the data file, never the HTML. Full contract: `dashboard/DASHBOARD_UPKEEP.md`.

Durable canonical copy: `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/`. Repo mirror: `~/Docs/Autonomous_business/docs/plan/green_path_2026-06/`. Full chronology: `handoff/SESSION_LOG_2026-06-12_to_13.md`.
