# Packets — Day 0, Phase -1, Phase 0, Phase 1

All packets inherit the Common packet rules in `00_README.md` §last. `<RUNTIME>` slots are filled by the orchestrator at dispatch.

---

## PKT-LINE31GUARD (Day 0 — orchestrator-executed, NOT delegated)

Not a /goal packet: the orchestrator performs this directly in the ads console context (external action, pre-authorized OD-008/020, the only pre-backup action). Steps: (1) export current LINE31 campaign budgets/creatives/targeting state to `green_path_run/line31_prechange_export_<ts>.json` (this IS the rollback artifact, RB-ADS); (2) pause creatives/targeting for sizes per YAML `OD-008.params.paused_sizes` (default 2XL/M/S); (3) set daily cap per `OD-020.params.cap_kzt_per_day` (default 10,000); (4) log action + verify next watcher ingest reflects it (kaspi_marketing.sqlite, mode=ro). Acceptance: spend cap visible in watcher data within 24h; zero spend attributed to paused sizes thereafter. Evidence → scoreboard prep for G-LINE31-01.

---

## PKT-BCK (Phase -1; Codex 5.5; holds BOTH repo leases for the freeze window)

/goal
Title: Phase -1 freeze, full backup, restore tests, manifest
Repo: ~/Docs/Autonomous_business (+ ~/Docs/Web_automation read-stage)
Branch/worktree: <RUNTIME: backup work writes only to the backup destination + run dir; no repo-content changes this packet>
Objective: G-BCK-01, G-BCK-02, G-BCK-03 green; G-ORD-04 verified after.
Context: DB is HOT (live order ingestion; CN-001). Ad-hoc backup practice exists (CN-059) — formalize it, don't duplicate. Freeze window per YAML OD-023.params (default ≤60min right after an ingest cycle; ingestion stays live; `sqlite3 .backup` online method).
Must-read: MASTER_REMEDIATION_PLAN.md §1/§4; green_gates.csv G-BCK-01..03; expert backup-scope table via dispositions.csv EXT-B01.
Allowed: backup destination dirs; green_path_run/; launchctl pause/resume of the write-capable jobs listed in your discovery (record list first).
Forbidden: ANY repo content edit; ANY DB write; deleting anything; reading secret VALUES (paths/checksums only).
Write permission: APPLY_ALLOWED_AFTER_GATE (the "writes" are backups + job pause/resume only).
Implementation requirements: capture git state both repos (branch/HEAD/remotes/dirty/untracked-operational); `sqlite3 .backup` for app.db + WA watcher DBs (+WAL/SHM if present); workbooks/configs/plists/exports/logs per EXT-B01 scope; secrets → private local backup, redacted manifest entries (path/sha256/secret_redacted=true); BACKUP_MANIFEST_<ts>.json; restore tests: 1 DB to scratch + `PRAGMA integrity_check`, 1 repo file, workbook checksums.
Commands: per discovery; all DB reads `mode=ro`; backup via `sqlite3 <db> ".backup <dest>"`.
Acceptance criteria: manifest complete (every class); 3 restore tests pass; freeze window ≤ agreed; post-window `python3 scripts/validate_kaspi_order_sync_freshness.py` exit 0; zero secret values anywhere.
Stop conditions: any backup class fails → STOP-THE-LINE (this is the one non-negotiable stop); restore test fails → same.
Return contract: per common rules + manifest path + restore-test log + the write-capable-job list discovered.

---

## PKT-READY (Phase 0; Codex 5.5; Opus review on the go/no-go table)

/goal
Title: Readiness — dry-run inventory, go/no-go table, rollback rehearsals, gating verification
Repo: ~/Docs/Autonomous_business
Branch/worktree: <RUNTIME>
Objective: G-RDY-01..04 + G-REPO-01..02 green.
Context: Every later write must pre-exist here as a go/no-go row with dry-run evidence. The two never-rehearsed rollbacks (cash-anchor reversal, stock-anchor supersession) get scratch-DB drills (G-RDY-02).
Must-read: plan §1–2; green_gates G-RDY-*; WRITE_APPLY_RUNBOOK.md; WRITE_SIDE_GATING_CONTRACT.md.
Allowed: green_path_run/; scratch dirs (e.g. /tmp/green_path_scratch); READ everything else.
Forbidden: live DB writes (scratch copies only — copy via the Phase -1 backup artifact, never the hot file); repo content changes except none.
Write permission: DRY_RUN_ONLY (live surfaces) / APPLY on scratch only.
Implementation requirements: enumerate every candidate write script (EOD, COGS backfill, entries backfill, ledger/anchor import, cashflow rebuild, bank anchor, FX import, ads sync/backfill, returns writers, quarantine triage, residual settlement, price/floor generation) → for each: command, env gates, dry-run output (before/after counts, row-diff sample), rollback ref, recommendation. Run `python3 scripts/validate_write_side_gating.py`. Rehearse RB-CASH-ANCHOR + RB-STOCK-ANCHOR on the scratch DB restored from backup. Stand up lease_log.md + DEFERRED_QUEUE.md skeletons. Run `pytest -q`, `scripts/check_no_db_tracked.sh`, `scripts/lint_docs.sh` baseline.
Acceptance criteria: go/no-go rows = 100% of write candidates; both rehearsals pass with documented restore queries; gating validator exit 0; baseline guards recorded (pass or pre-existing-failure catalogued, never "fixed" silently here).
Stop conditions: a write script lacks dry-run mode or apply gate → record as go/no-go=NO + park (its lane redesigns around it); do not patch scripts in this packet.
Return contract: common + go_no_go.md path + rehearsal logs.

---

## PKT-INFRA-SCHED (Phase 1; Codex 5.5; AB lease for plist/venv edits)

/goal
Title: Scheduler repair — stable venv, repoint 8 jobs, per-job EX_CONFIG diagnosis, supervised EOD
Repo: ~/Docs/Autonomous_business
Branch/worktree: <RUNTIME>
Objective: G-SCHED-01, G-SCHED-02 (dry-run first; apply per YAML OD-015.params.eod_apply), G-SCHED-03 green; G-BCK-04 with PKT-INFRA-ALERT's offsite lane.
Context: CRITICAL NUANCE (CN-048/049): /opt/homebrew/bin/python3 reappeared 2026-06-12 as dep-less python3.14 (brew) — do NOT rely on it; kaspi-marketing-hourly now exit 1 on missing yaml. end-of-day's exit 78 is NOT interpreter-missing (its .venv python 3.12.4 runs) — diagnose its EX_CONFIG cause per-job (plist syntax, WorkingDirectory, missing env file, permissions). 7 jobs still exit 78. All job logs frozen 2026-02-12..14.
Must-read: plan §1/§4 RB-PLIST; green_gates G-SCHED-01..03; the plist files in ~/Library/LaunchAgents (com.example.*, com.autonomous-business.*); logs/end_of_day.log tail.
Allowed: a repo-owned venv (create/pin deps); the 8+ plist files (backed up by Phase -1); logs/ reading; green_path_run/.
Forbidden: deleting jobs; touching ingestion-path jobs beyond interpreter/env lines without diagnosis; DB writes (EOD apply is the single exception, AFTER its dry-run + OD-015 check + orchestrator ACCEPT).
Write permission: PATCH_ALLOWED (plists/venv) / APPLY_ALLOWED_AFTER_GATE (EOD only).
Implementation requirements: build/pin venv with every job's imports (walk each job script's deps); repoint ProgramArguments per job; per-job root-cause table for the 78s; `launchctl bootout`+`bootstrap` each; verify spawn via `launchctl print` + fresh log lines; EOD: validation/dry-run mode first, save output, then apply per OD-015 under orchestrator ACCEPT; after EVERY job change run validate_kaspi_order_sync_freshness.py.
Acceptance criteria: 8/8 LastExitStatus=0; validate_scheduler_heartbeat.py exit 0; EOD dry-run clean + (if authorized) one supervised apply with STATUS: SUCCESS; root-cause table complete.
Stop conditions: a job's failure cause needs a business-rule change → park to its Phase-2 lane; EOD apply diff exceeds OD-015 tolerance → halt + Opus review.
Return contract: common + per-job before/after exit codes + venv manifest.

---

## PKT-INFRA-ALERT (Phase 1; Codex 5.5; parallel with PKT-INFRA-SCHED — disjoint files)

/goal
Title: Alerting + offsite backup — Telegram plumbing, forced-failure proof, offsite lane
Repo: ~/Docs/Autonomous_business
Branch/worktree: <RUNTIME>
Objective: G-ALERT-01, G-ALERT-02 (window starts), G-BCK-04 green.
Context: Keys already EXIST in repo .env (CN-050) and were live-validated in the owner session (YAML OD-031.params.live_test_message_received must be true — check it). Jobs don't load .env → plumb env into job environments (EnvironmentVariables or a sourced env wrapper — match repo convention). 66/66 alerts skipped to date. Alerting WORKED before 2026-02-13 (end_of_day.log proves the code path).
Must-read: green_gates G-ALERT-*; the alert-sending code paths (grep 'Telegram alert' scripts/); plist EnvironmentVariables blocks.
Allowed: plist env blocks / env-wrapper scripts; green_path_run/.
Forbidden: printing/logging token values ANYWHERE (presence checks only); touching ProgramArguments (PKT-INFRA-SCHED owns those lines — coordinate via orchestrator if same file: SCHED holds the plist lease first, ALERT patches after).
Write permission: PATCH_ALLOWED.
Implementation requirements: plumb env to ALL business jobs; trigger ONE controlled forced failure (e.g. run the preflight against a deliberately-missing scratch input, or its test hook if present) → verify message received; restore offsite backup job (destination per YAML OD-024.params.destination_ref; write-test was done in-session) → one full cycle + spot restore.
Acceptance criteria: forced-failure alert receipt logged (redacted screenshot/message-id); 0 'alert skipped' lines in the next scheduled runs; offsite cycle + spot-restore pass.
Stop conditions: test message NOT received though YAML says in-session test passed → STOP-THE-LINE (credential drift = owner data needed).
Return contract: common + receipt evidence + offsite cycle log.
