# Agent 8 - Daily Runner, Reports, Release Gates Executor

Before executing, read:
1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-03_operational-stock-truth-system/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-03_operational-stock-truth-system/08_AGENT_8__DAILY_RUNNER_RELEASE__AFTER_07.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_operational-stock-truth-system/agent_7_orders_po_ads_cashflow_closeout.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_operational-stock-truth-system/orchestrator_gate_decision_after_agent7.md`

Role:

- Sequential write-capable implementation agent.
- You are not alone in the codebase. Do not revert edits made by others. Reread live files before editing.
- DB writes require backup, explicit apply gate, and rollback instructions.

Task:

- Create or harden the strict daily truth runner.
- Add run lineage, source manifests, validation results, exception queue/reporting, owner trust banners, and release gates.
- Ensure the business gets an always-current stock snapshot or a red blocked brief without manual recalculation.
- Because Agent 7's live integration gate is RED, this execution is fail-closed mode only. Do not publish green business/release status unless the blockers are actually resolved and verified.

Required tests before changes:

- Runner fail-closed fixture.
- Source freshness fixture.
- Report lineage fixture.
- Red owner brief fixture.
- Scheduler/interpreter determinism fixture.

Suggested closeout:

- `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_operational-stock-truth-system/agent_8_daily_runner_release_closeout.md`

Required verification:

- Focused runner/report tests.
- `python3 scripts/validate_params.py --strict`
- `python3 scripts/run_end_of_day.py --verbose` only if safe in current repo state.
- `pytest -q` when practical for release candidate.
- `scripts/check_no_db_tracked.sh`
- `scripts/lint_docs.sh` if docs are touched.

Stop if:

- Agent 7 closeout is missing, or the orchestrator gate decision after Agent 7 is missing or not green.
- The runner catches hard failures and still publishes green outputs.
- Any required gate is skipped without being explicitly recorded as a blocker.
