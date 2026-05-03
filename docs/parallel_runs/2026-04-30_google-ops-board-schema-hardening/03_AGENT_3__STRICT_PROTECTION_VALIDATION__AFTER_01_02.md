# Agent 3 — Strict Protection Validation

Before executing, read:
1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-04-30_google-ops-board-schema-hardening/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-04-30_google-ops-board-schema-hardening/03_AGENT_3__STRICT_PROTECTION_VALIDATION__AFTER_01_02.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-04-30_google-ops-board-schema-hardening/agent_1_auto_repair_closeout.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-04-30_google-ops-board-schema-hardening/agent_2_schema_canary_closeout.md`

Role

- Sequential write-capable execution agent for stricter Google Sheet protection validation after Agents 1 and 2 complete.

Do not start if

- Agent 1 or Agent 2 closeout is missing or not complete.
- Agent 3 closeout already exists and says complete: `~/Docs/Autonomous_business_agent_handoffs/2026-04-30_google-ops-board-schema-hardening/agent_3_protection_validation_closeout.md`

Task

- Add stricter validation that live Google Sheet protections match the employee-facing contract:
- `SalesRaw_Today`: only `MY_SIZE` is unprotected for operator rows.
- `Run_Control`: only `ready_for_closeout` is unprotected for operator rows.
- Protected ranges must not be warning-only.
- The validation report should fail closed when protections are missing, too broad, warning-only, or expose extra editable columns.

Suggested read targets

- `~/Docs/Autonomous_business/config/google_ops_board.yaml`
- `~/Docs/Autonomous_business/core/integrations/google_ops_board.py`
- `~/Docs/Autonomous_business/scripts/sync_google_ops_board.py`
- `~/Docs/Autonomous_business/scripts/run_google_ops_board_prewindow_health.py`
- `~/Docs/Autonomous_business/tests/test_google_ops_board.py`
- `~/Docs/Autonomous_business/tests/test_google_ops_board_prewindow_health.py`

Implementation notes

- Write tests before code changes.
- Use Google Sheets API metadata, not assumptions from YAML alone, for live validation.
- If live protection apply is run, record before/after metadata and exact write-enable env gate.
- Do not run Kaspi shipping, waybill build, Telegram production bundle send, WhatsApp send, or DB mutation.

Required verification

- Focused pytest for exact-protection pass and over-broad/unprotected/warning-only failures.
- `git diff --check`
- `scripts/check_no_db_tracked.sh`
- `scripts/lint_docs.sh` if docs are touched.

Closeout

- Write results, commands, files changed, artifacts, and rollback notes to `~/Docs/Autonomous_business_agent_handoffs/2026-04-30_google-ops-board-schema-hardening/agent_3_protection_validation_closeout.md`.
