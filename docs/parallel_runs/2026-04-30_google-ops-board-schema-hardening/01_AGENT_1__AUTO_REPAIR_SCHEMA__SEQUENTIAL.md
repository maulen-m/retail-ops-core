# Agent 1 — Auto-Repair Blank Spacer Columns

Before executing, read:
1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-04-30_google-ops-board-schema-hardening/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-04-30_google-ops-board-schema-hardening/01_AGENT_1__AUTO_REPAIR_SCHEMA__SEQUENTIAL.md`

Role

- Sequential write-capable execution agent for Google Ops Board blank-spacer schema repair.

Do not start if

- Agent 1 closeout already exists and says complete: `~/Docs/Autonomous_business_agent_handoffs/2026-04-30_google-ops-board-schema-hardening/agent_1_auto_repair_closeout.md`

Task

- Implement a deterministic repair path for `SalesRaw_Today` header rows where the non-blank observed headers exactly match the contract headers but one or more blank spacer columns were inserted.
- Preserve employee-entered `MY_SIZE` by stable key (`_db_row_id` / `_line_key` where applicable) and never shift sizes positionally.
- Repair should be safe for closeout/publish paths and should leave non-blank unknown headers or missing required headers as blocking failures.

Suggested read targets

- `~/Docs/Autonomous_business/core/integrations/google_ops_board.py`
- `~/Docs/Autonomous_business/scripts/sync_google_ops_board.py`
- `~/Docs/Autonomous_business/scripts/run_google_ops_board_prewindow_health.py`
- `~/Docs/Autonomous_business/tests/test_google_ops_board.py`
- `~/Docs/Autonomous_business/tests/test_google_ops_board_prewindow_health.py`

Implementation notes

- Write fail-first tests proving a blank spacer column can be repaired without losing `MY_SIZE`.
- Add before/after repair artifact output for layout drift.
- If a live Google Sheet repair is run, snapshot the affected tab first and record the artifact path.
- Do not run Kaspi shipping, waybill build, Telegram bundle send, WhatsApp send, or DB mutation.

Required verification

- Focused pytest covering the new repair path.
- `git diff --check`
- `scripts/check_no_db_tracked.sh`
- `scripts/lint_docs.sh` if docs are touched.

Closeout

- Write results, commands, files changed, artifacts, and rollback notes to `~/Docs/Autonomous_business_agent_handoffs/2026-04-30_google-ops-board-schema-hardening/agent_1_auto_repair_closeout.md`.
