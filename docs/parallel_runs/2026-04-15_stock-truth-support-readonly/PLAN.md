PLAN

Title

- Stock Truth Support Read-Only Rollout

Purpose

- Run parallel read-only stock-truth support analysis for the active PO/cash/stock integrity rollout, using the Web_automation March 2 helper snapshot and the external stock-audit workbook to help the owner and current Agent A judge reconstructed stock safely.

Repo

- `~/Docs/Autonomous_business`

Canonical protocol

- `docs/PARALLEL_EXECUTION_PROTOCOL.md`

Read first

- `AGENTS.md`
- `docs/00_START_HERE.md`
- `docs/PARALLEL_EXECUTION_PROTOCOL.md`
- `docs/ops/STOCK_SNAPSHOT_RUNBOOK.md`
- `docs/DAILY_SOP.md`

Execution posture

- support-only, read-mostly rollout
- Agent B and Agent C launch now in parallel
- current main Agent A keeps executing the primary repair and is not replaced by this pack
- no new repo writer starts from this support rollout unless the owner explicitly asks later

Shared handoff folder

- `~/Docs/Autonomous_business_agent_handoffs/2026-04-15_stock-truth-support-readonly`

As-of window

- `2026-04-15`

External truth candidates for this support run

- `~/Docs/Web_automation/exports/stock_snapshots/2.3.26/stock_snapshot_2.3.2026_1.xlsx`
- `~/Docs/Oracle/Autonomous_business/2026-04-04/stock_audit_2026-04-04.xlsx`
- `~/Docs/Oracle/Autonomous_business/2026-04-04/backups/stock_audit_2026-04-04.20260404_225313_235600.xlsx`
- `~/Docs/Oracle/Autonomous_business/2026-04-04/MEMO_stock_audit_handoff_2026-04-15.md`

Primary repo-side stock paths for this support run

- `~/Docs/Autonomous_business/excel/stock_snapshot_2.3.2026.xlsx`
- `~/Docs/Autonomous_business/config/anchors/STOCK_SNAPSHOT_LATEST.xlsx`
- `~/Docs/Autonomous_business/scripts/sync_current_stock.py`
- `~/Docs/Autonomous_business/scripts/reconcile_ledger_to_snapshot.py`
- `~/Docs/Autonomous_business/scripts/daily_pipeline_v2.py`
- `~/Docs/Autonomous_business/scripts/ingest_sales_v2.py`

Role split

Agent B

- read-only source-comparison analyst
- compare March 2 helper snapshot, repo March 2 stock snapshot, external audit workbook, and any supporting memo evidence
- decide which source is closest to warehouse truth and where the known operator facts conflict with the computed model

Agent C

- read-only reconstruction-method analyst
- inspect ledger/movement logic, warehouse-vs-offer divergence, missing movement classes, and whether the provisional reconstruction is safe enough to continue downstream

Agent A

- optional later consumer only
- do not launch a second writer right now
- use this prompt only if the owner wants the current executing Agent A to consume the support findings

Questions this support run must answer

1. Is the current reconstructed stock directionally credible enough to continue as provisional truth?
2. Which SKU-size families still conflict materially with known operator facts?
3. Are the conflicts more likely caused by:
   - missing warehouse adjustments
   - alias/canonicalization issues
   - offer-stock vs warehouse-stock confusion
   - sales/returns movement gaps
4. What exact rule should gate continuation:
   - continue with provisional stock and manual review later
   - continue only after named SKU fixes
   - stop until a new canonical stock workbook exists

Required outputs

- `agent_b_report.md`
- `agent_c_report.md`
- `status_board.md`
- optional `agent_a_execution_log.md` only if the owner later asks the active Agent A to consume this support pack

Launch order

1. Agent B
2. Agent C
3. no Agent A launch from this pack unless explicitly requested

Rules

- B and C are read-only
- B and C do not read each other before publishing first-pass findings
- no repo writes
- no DB writes
- no touching the main active Agent A worktree or execution log
- findings should be source-backed and curation-friendly for the owner

Success criteria

- the owner gets a clear support judgment on whether the current stock reconstruction path is safe to continue
- the owner gets a ranked list of remaining stock-truth risks
- the owner gets a minimal curation instruction they can pass to the active Agent A if needed
