# Agent 8 - Residual Corrected-Window Writer After Agent 7

You are Agent 8 in the green-path Phase 2 run.

Repo: `~/Docs/Autonomous_business`

Assigned closeout:
`~/Docs/Autonomous_business_agent_handoffs/20260614_green_path_remaining_phase2/agent8_residual_corrected_window_writer_closeout.md`

## Scope

Lane: PKT-RESID / `G-RESID-01` only.

Objective: settle the verified 10-row on-delivery residual set using the corrected report window only if dry-run evidence proves the write scope is exactly those 10 rows and no others.

Current accepted DB boundary before this lane:

- `db/app.db` SHA256: `8f7b72c2b758fa6370bdf21935dce15586ebe7672b095f0c020c0ecce939ab9b`

Authority/evidence context:

- OD-015 pre-authorizes supervised residual settlement applies after dry-run, scoped diff, backup, alert path, and no out-of-scope rows.
- Agent7 stopped without DB write because exact `--since 2026-06-14 --until 2026-06-14` had `0` candidates.
- Agent7 diagnostic proved the referenced 10-row report is a `MIN..2026-06-14` window, still current, and all 10 referenced orders have `status_updated_at=2026-06-13`.
- Agent7 diagnostic total balance: `33,053.01` KZT.

Required exact 10 order IDs:

- `952481483`
- `953335378`
- `953810922`
- `954632568`
- `954926607`
- `954946245`
- `955006324`
- `955150514`
- `956352089`
- `956352766`

## Must Read

- `AGENTS.md`
- `docs/00_START_HERE.md`
- `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/green_path_run/STATUS.md`
- `~/Docs/Autonomous_business_agent_handoffs/20260614_green_path_remaining_phase2/agent7_residual_settlement_writer_closeout.md`
- `~/Docs/Autonomous_business/exports/validation/residual_settlement_20260614_20260614_084851/diagnostic_min_to_20260614/on_delivery_residuals_2026-06-14_20260614_085032.md`
- `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/OWNER_DECISIONS_RECORDED.yaml` OD-015
- `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/starter_pack/03_packets_phase2.md` residual section
- `scripts/reconcile_on_delivery_settlement.py`
- `scripts/check_on_delivery_residuals.py`
- `scripts/validate_on_delivery_freeze.py`

Use the `write-gated-db-repair` skill if available.

## Allowed

- Read-only inspection.
- Scratch proof if useful.
- Production DB mutation only through `scripts/reconcile_on_delivery_settlement.py` with `ENABLE_CASHFLOW_WRITE=1` and `--apply`, after backup and dry-run scope proof.
- Evidence under `exports/validation/residual_corrected_window_20260614_<timestamp>/`.
- Closeout file.

## Forbidden

- Do not edit dashboard files, `green_path_run/scoreboard.csv`, `green_path_run/STATUS.md`, or the Oracle workspace mirror. The orchestrator updates live state after verifying your closeout.
- No external systems: no Telegram sends, LaunchAgent loads/unloads, browser/Chrome, Kaspi, Repricer, Binance/bank, workbook writes, customer/operator messages.
- No COGS authority changes, stock writes, cash anchor writes, returns writes, pricing writes, ads writes, quarantine writes, or broad refactors.
- Do not change code unless the existing script is demonstrably broken; if code would be required, stop with `Gate: YELLOW`.

## Required Procedure

1. Confirm starting DB SHA equals `8f7b72c2b758fa6370bdf21935dce15586ebe7672b095f0c020c0ecce939ab9b`.
2. Verify daily ops are paused:
   - `.venv/bin/python scripts/manage_business_automation.py verify --scope daily-ops --expect paused`
3. Run before residual report with the corrected window:
   - `.venv/bin/python scripts/check_on_delivery_residuals.py --db db/app.db --until 2026-06-14 --output-dir <evidence>/before`
4. Stop with `Gate: YELLOW` if the before report is not exactly the 10 order IDs listed above.
5. Create a production DB backup before any live write. Record backup path, SHA, and `PRAGMA integrity_check`.
6. Run dry-run with corrected window and save transcript:
   - `.venv/bin/python scripts/reconcile_on_delivery_settlement.py --db db/app.db --until 2026-06-14 --run-id residual_corrected_window_20260614_<timestamp>`
7. Stop with `Gate: YELLOW` if dry-run does not propose exactly the same 10 order IDs and total `33,053.01` KZT, or if any out-of-scope row appears.
8. Apply only if scope proof passes:
   - `ENABLE_CASHFLOW_WRITE=1 .venv/bin/python scripts/reconcile_on_delivery_settlement.py --db db/app.db --until 2026-06-14 --run-id residual_corrected_window_20260614_<timestamp> --apply`
9. Capture after evidence:
   - final DB SHA and integrity,
   - row/event counts written by run id,
   - after residual report with `--until 2026-06-14`,
   - after exact-window report with `--since 2026-06-14 --until 2026-06-14`,
   - `scripts/check_no_db_tracked.sh`,
   - `.venv/bin/python scripts/validate_on_delivery_freeze.py --db db/app.db --until 2026-06-14`,
   - `.venv/bin/python scripts/validate_cashflow_invariants.py --db db/app.db`.
10. Write rollback instructions using the real backup path.

## Gate Rules

`Gate: GREEN` only if:

- production apply completed,
- before/dry-run scope exactly matched the 10 rows and no others,
- after `--until 2026-06-14` residual count is `0`,
- `validate_on_delivery_freeze.py --until 2026-06-14` passes,
- `validate_cashflow_invariants.py` passes,
- DB guard passes,
- closeout includes backup, rollback, pre/post SHA, before/dry-run/apply/after report paths, and exact command transcripts.

`Gate: YELLOW` if no unsafe write happened but authority/scope/code/data needs orchestrator decision.

`Gate: RED` only for a failed or partially applied write, data-loss risk, rollback need, or validator regression.

## Closeout Format

Start with:

```markdown
# Agent 8 - Residual Corrected-Window Writer Closeout

Gate: GREEN|YELLOW|RED
```

Then include: scope, result, files changed, DB backup/rollback, pre/post SHA, before/dry-run/apply/after evidence, validators, and remaining blockers.
