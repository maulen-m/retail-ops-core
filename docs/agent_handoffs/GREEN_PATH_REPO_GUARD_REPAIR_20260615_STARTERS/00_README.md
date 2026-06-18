# Green Path Repo Guard Repair 2026-06-15 Starters

Goal: reduce the current full-suite repo guard failures after the 2026-06-15 13:18 pytest inventory.

Shared constraints for all agents:

- Repo: `~/Docs/Autonomous_business`
- Branch: `greenpath/20260613-phase2-truth`
- Do not write production `db/app.db`.
- Do not write workbooks.
- Do not change LaunchAgents, Telegram, Google board, Kaspi, Repricer, Chrome/browser state, or external systems.
- Do not edit dashboard/progress/status/scoreboard/session files; the orchestrator owns them.
- Keep edits scoped to assigned scripts/tests/docs only.
- Write assigned closeout first, with a standalone `Gate: GREEN|YELLOW|RED`.
- Run focused tests for assigned failures, plus `bash scripts/lint_docs.sh`, `bash scripts/check_no_db_tracked.sh`, and scoped `git diff --check`.

Full-suite baseline to repair:

- `.venv/bin/python -m pytest -q`
- Result at 2026-06-15 13:18 +05: `38 failed, 3488 passed, 4 skipped`.

Agents:

- Agent 1: LINE31 downstream current-state contracts.
- Agent 2: PO dashboard and schedule contracts.
- Agent 3: operational CLI/import/sync/waybill contracts.
- Agent 4: WebUI archive and owner-truth contracts.
- Agent 5: validator output/semantics contracts.

