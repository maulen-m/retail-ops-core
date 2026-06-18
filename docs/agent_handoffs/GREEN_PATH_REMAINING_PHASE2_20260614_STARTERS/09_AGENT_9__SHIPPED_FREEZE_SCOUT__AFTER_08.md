# Agent 9 - Shipped Freeze Scout After Residual Settlement

You are Agent 9 in the green-path Phase 2 run.

Repo: `~/Docs/Autonomous_business`

Assigned closeout:
`~/Docs/Autonomous_business_agent_handoffs/20260614_green_path_remaining_phase2/agent9_shipped_freeze_scout_closeout.md`

## Scope

Read-only scout for the retained `validate_on_delivery_freeze.py --until 2026-06-14` failures after Agent8.

Current accepted DB boundary:

- `db/app.db` SHA256: `2c654acab422b86ee15448dc69d2041194ec834d5246e4c57148d0feef6c9b37`

Known retained class:

- 19 rows: `status=SHIPPED has missing INVENTORY_ON_DELIVERY_COST balance`
- This class remained after Agent8 settled the 10 completed residual rows.

## Must Read

- `AGENTS.md`
- `docs/00_START_HERE.md`
- `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/green_path_run/STATUS.md`
- `~/Docs/Autonomous_business_agent_handoffs/20260614_green_path_remaining_phase2/agent8_residual_corrected_window_writer_closeout.md`
- `scripts/validate_on_delivery_freeze.py`
- `scripts/check_on_delivery_residuals.py`
- `docs/KASPI_ORDER_CASHFLOW_TRACKING.md`
- Any local lifecycle/status source docs needed to classify these 19 rows.

## Forbidden

- No DB writes, no `--apply`, no env-gated writes.
- Do not edit dashboard, scoreboard, STATUS, Oracle workspace mirror, code, plists, LaunchAgents, Telegram, Kaspi, Repricer, browser, workbook, pricing, COGS, stock, returns, or customer/operator-message surfaces.
- Do not run external live actions. Read-only local DB/file inspection only.

## Required Work

1. Verify the DB SHA starts at `2c654acab422b86ee15448dc69d2041194ec834d5246e4c57148d0feef6c9b37`.
2. Run and capture the current validator failure:
   - `bash -o pipefail -c '.venv/bin/python scripts/validate_on_delivery_freeze.py --db db/app.db --until 2026-06-14 | tee <evidence>/validate_on_delivery_freeze.txt'`
3. Extract the 19 order IDs and classify each:
   - current order status and status source/date,
   - whether it has order entries/SKU identity,
   - whether it has cashflow events for `INVENTORY_ON_DELIVERY_COST`,
   - whether it has shipped/waybill/API evidence that should carry on-delivery cost,
   - whether the correct repair is status update, missing on-delivery cost recognition, quarantine, or wait for live shipment lifecycle.
4. Identify existing repo scripts or prior contracts that can repair this class. Prefer existing scripts; do not propose ad hoc SQL unless there is no repo-owned path.
5. Produce a recommended next writer plan if safe:
   - exact script/command,
   - env gate,
   - backup/dry-run/apply/readback/validator sequence,
   - expected row count/scope,
   - stop rules.

## Closeout Gate

Use:

- `Gate: GREEN` if the read-only classification is complete and recommends a safe next action or proves the class should be parked.
- `Gate: YELLOW` if more evidence or owner/orchestrator authority is required before a writer can be defined.
- `Gate: RED` only if you discover data loss, unexpected post-Agent8 regression, or a live safety issue.

Closeout must include a standalone line: `Gate: <GREEN/YELLOW/RED>`.

