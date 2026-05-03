# Agent 2 — Telegram Schema Canary

Before executing, read:
1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-04-30_google-ops-board-schema-hardening/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-04-30_google-ops-board-schema-hardening/02_AGENT_2__TELEGRAM_SCHEMA_CANARY__AFTER_01.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-04-30_google-ops-board-schema-hardening/agent_1_auto_repair_closeout.md`

Role

- Sequential write-capable execution agent for schema canary alerting after Agent 1 completes.

Do not start if

- Agent 1 closeout is missing or not complete.
- Agent 2 closeout already exists and says complete: `~/Docs/Autonomous_business_agent_handoffs/2026-04-30_google-ops-board-schema-hardening/agent_2_schema_canary_closeout.md`

Task

- Add a pre-closeout schema canary that reports Google Ops Board layout drift clearly before closeout proceeds.
- If blank spacer columns are auto-repaired, alert owner/Telegram with the repaired tab and column numbers.
- If non-repairable drift remains, alert owner/Telegram with the exact tab, expected headers, observed headers, and closeout-blocking reason.

Suggested read targets

- `~/Docs/Autonomous_business/scripts/run_google_ops_board_prewindow_health.py`
- `~/Docs/Autonomous_business/scripts/run_google_ops_board_closeout.py`
- `~/Docs/Autonomous_business/core/alerts/google_ops_board_alerts.py`
- `~/Docs/Autonomous_business/core/integrations/telegram_bot.py`
- `~/Docs/Autonomous_business/tests/test_google_ops_board_prewindow_health.py`
- `~/Docs/Autonomous_business/tests/test_google_ops_board_closeout.py`

Implementation notes

- Write tests before code changes.
- Prefer existing owner alert / Telegram config helpers over adding a new delivery channel.
- Do not send live Telegram test messages unless explicitly needed and marked as a test; mocked tests are preferred.
- Do not run Kaspi shipping, waybill build, Telegram production bundle send, WhatsApp send, or DB mutation.

Required verification

- Focused pytest covering repaired-drift alert and blocking-drift alert.
- `git diff --check`
- `scripts/check_no_db_tracked.sh`
- `scripts/lint_docs.sh` if docs are touched.

Closeout

- Write results, commands, files changed, artifacts, and rollback notes to `~/Docs/Autonomous_business_agent_handoffs/2026-04-30_google-ops-board-schema-hardening/agent_2_schema_canary_closeout.md`.
