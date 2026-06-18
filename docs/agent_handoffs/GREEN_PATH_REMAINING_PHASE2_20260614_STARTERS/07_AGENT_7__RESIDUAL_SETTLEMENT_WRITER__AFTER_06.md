# Agent 7 - Residual Settlement Writer After Cash Anchor

You are Agent 7 in the green-path Phase 2 run.

Repo: `~/Docs/Autonomous_business`

Assigned closeout:
`~/Docs/Autonomous_business_agent_handoffs/20260614_green_path_remaining_phase2/agent7_residual_settlement_writer_closeout.md`

## Scope

Lane: PKT-RESID / `G-RESID-01` only.

Objective: safely settle the current on-delivery residual set if and only if it is exactly the live 2026-06-14 residual class and the write remains inside OD-015-style dry-run/backup/apply gates.

Expected current residual evidence:

- Report: `~/Docs/Autonomous_business/exports/on_delivery_residuals/on_delivery_residuals_2026-06-14_20260614_080623.md`
- Residual count: `10`
- Window: `2026-06-14` to `2026-06-14`
- Apply command shape: `ENABLE_CASHFLOW_WRITE=1 .venv/bin/python scripts/reconcile_on_delivery_settlement.py --since 2026-06-14 --until 2026-06-14 --apply`

Current accepted DB boundary before this lane:

- `db/app.db` SHA256: `8f7b72c2b758fa6370bdf21935dce15586ebe7672b095f0c020c0ecce939ab9b`

## Must Read

- `AGENTS.md`
- `docs/00_START_HERE.md`
- `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/green_path_run/STATUS.md`
- `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/starter_pack/03_packets_phase2.md` residual section
- `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/OWNER_DECISIONS_RECORDED.yaml` OD-015
- `~/Docs/Autonomous_business_agent_handoffs/20260614_green_path_remaining_phase2/agent4_returns_quar_sched_scout_closeout.md`
- `~/Docs/Autonomous_business/exports/on_delivery_residuals/on_delivery_residuals_2026-06-14_20260614_080623.md`
- `scripts/reconcile_on_delivery_settlement.py`
- `scripts/check_on_delivery_residuals.py`
- `scripts/validate_on_delivery_freeze.py`

Use the `write-gated-db-repair` skill if available. This lane mutates `db/app.db` only through the governed residual settlement script.

## Allowed

- Read-only inspection.
- Scratch DB proof.
- Production DB mutation only through `scripts/reconcile_on_delivery_settlement.py` with `ENABLE_CASHFLOW_WRITE=1` and `--apply`, after backup and dry-run evidence pass.
- Evidence under `exports/validation/residual_settlement_20260614_<timestamp>/`.
- Closeout file.

## Forbidden

- Do not edit dashboard files, `green_path_run/scoreboard.csv`, `green_path_run/STATUS.md`, or the Oracle workspace mirror. The orchestrator updates live state after verifying your closeout.
- No external systems: no Telegram sends, LaunchAgent loads/unloads, browser/Chrome, Kaspi, Repricer, Binance/bank, workbook writes, customer/operator messages.
- No COGS authority changes, stock writes, cash anchor writes, returns writes, pricing writes, ads writes, or broad refactors.
- Do not change code unless the existing script is demonstrably broken; if code would be required, stop with `Gate: YELLOW` and explain.

## Required Procedure

1. Confirm starting DB SHA equals `8f7b72c2b758fa6370bdf21935dce15586ebe7672b095f0c020c0ecce939ab9b`.
2. Verify daily ops are still paused:
   - `.venv/bin/python scripts/manage_business_automation.py verify --scope daily-ops --expect paused`
3. Run a fresh before residual report for `2026-06-14` only into your evidence root:
   - `.venv/bin/python scripts/check_on_delivery_residuals.py --db db/app.db --since 2026-06-14 --until 2026-06-14 --output-dir <evidence>/before`
4. Compare the fresh before report to the 10 rows in the existing report. Stop with `Gate: YELLOW` if:
   - count is not exactly `10`,
   - any order id/SKU differs,
   - dry-run proposes rows outside that exact set,
   - the current set is not reasonably covered by the OD-015 residual settlement approval.
5. Create a production DB backup before any live write. Record backup path and `PRAGMA integrity_check`.
6. Run dry-run on production DB for the exact window and save stdout/stderr:
   - `.venv/bin/python scripts/reconcile_on_delivery_settlement.py --db db/app.db --since 2026-06-14 --until 2026-06-14 --run-id residual_settlement_20260614_<timestamp>`
7. If dry-run scope matches exactly, apply:
   - `ENABLE_CASHFLOW_WRITE=1 .venv/bin/python scripts/reconcile_on_delivery_settlement.py --db db/app.db --since 2026-06-14 --until 2026-06-14 --run-id residual_settlement_20260614_<timestamp> --apply`
8. Capture after evidence:
   - final DB SHA and integrity,
   - row/event counts written by run id,
   - after residual report for `2026-06-14`,
   - `scripts/check_no_db_tracked.sh`,
   - `.venv/bin/python scripts/validate_on_delivery_freeze.py --db db/app.db --since 2026-06-14 --until 2026-06-14`,
   - `.venv/bin/python scripts/validate_cashflow_invariants.py --db db/app.db`.
9. Write rollback instructions using the real backup path.

## Gate Rules

`Gate: GREEN` only if:

- production apply completed,
- before set matched the exact current 10 residuals,
- after residual count is `0` for the same window,
- `validate_on_delivery_freeze.py` passes for the same window,
- `validate_cashflow_invariants.py` passes,
- DB guard passes,
- closeout includes backup, rollback, pre/post SHA, before/after report paths, and exact command transcripts.

`Gate: YELLOW` if no unsafe write happened but authority/scope/code/data needs orchestrator decision.

`Gate: RED` only for a failed or partially applied write, data-loss risk, rollback need, or validator regression.

## Closeout Format

Start with:

```markdown
# Agent 7 - Residual Settlement Writer Closeout

Gate: GREEN|YELLOW|RED
```

Then include: scope, result, files changed, DB backup/rollback, pre/post SHA, before/dry-run/apply/after evidence, validators, and remaining blockers.
