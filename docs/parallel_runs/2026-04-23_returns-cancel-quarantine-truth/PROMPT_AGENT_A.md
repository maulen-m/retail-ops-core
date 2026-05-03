# PROMPT_AGENT_A — Execute Return/Cancel Quarantine Truth Rollout

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-04-23_returns-cancel-quarantine-truth/PLAN.md`
5. `~/Docs/Autonomous_business_agent_handoffs/2026-04-23_returns-cancel-quarantine-truth/agent_b_report.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-04-23_returns-cancel-quarantine-truth/agent_c_report.md`
7. this prompt

Shared handoff folder:

- `~/Docs/Autonomous_business_agent_handoffs/2026-04-23_returns-cancel-quarantine-truth`

## Role

You are Agent A, the only write-capable execution agent for this rollout.

Start only after Agent B and Agent C have published first-pass reports.

## Objective

Implement the smallest safe version of all four requested tracks:

1. deterministic return/cancel backlog export
2. quarantine ledger/export contract
3. employee QC queue surface for future manual processing
4. daily automation hook or precise implementation stopline

Manual employee recount/QC is not available yet. Do not infer QC outcomes.

## Required Business Rule

Returned units do not return to active stock automatically.

Use this treatment unless Agent B/C prove a safer repo-owned rule:

- `COMPLETED` / delivered: count as sale, deduct active stock.
- `CANCELLED` before shipment/handover: exclude from sales; no active-stock add-back.
- `CANCELLING` / `RETURN_REQUESTED`: expected return exposure; no active-stock add-back.
- `RETURNED` / `returnedToWarehouse=true`: quarantine stock candidate; no active-stock add-back.
- future employee QC pass: only then move quarantine to active stock.

## Implementation Order

1. Read B and C reports.
2. If B/C materially conflict, write a stopline summary before coding.
3. Add tests first for any new classifier/export behavior.
4. Implement a read-only backlog export first.
5. Add quarantine export/ledger only behind gates if DB writing is needed.
6. Add employee QC queue export with all rows defaulting to `PENDING_QC`.
7. Add daily automation hook only if safe and small; otherwise document a precise stopline.
8. Run relevant gates.
9. Update execution log and status board.

## Expected Outputs

Prefer:

- `exports/returns_quarantine/<as_of>/return_cancel_backlog.csv`
- `exports/returns_quarantine/<as_of>/return_cancel_summary.md`
- `exports/returns_quarantine/<as_of>/return_cancel_exceptions.csv`
- `exports/returns_quarantine/<as_of>/employee_qc_queue.csv`

If DB write path is added:

- require `ENABLE_RETURN_QUARANTINE_WRITE=1`
- require `--apply`
- create DB backup first
- record backup path and rollback command

## Required Validation

Minimum:

- targeted tests for new logic
- `python3 scripts/validate_params.py --strict`
- `scripts/check_no_db_tracked.sh`

If docs touched:

- `scripts/lint_docs.sh`

If DB touched:

- backup path in execution log
- restore command in execution log
- relevant DB invariants

## Output

Write:

- `~/Docs/Autonomous_business_agent_handoffs/2026-04-23_returns-cancel-quarantine-truth/agent_a_execution_log.md`
- update `~/Docs/Autonomous_business_agent_handoffs/2026-04-23_returns-cancel-quarantine-truth/status_board.md`

Include:

- ordered actions
- commands run
- output paths
- pass/fail gates
- remaining stoplines
- rollback steps
