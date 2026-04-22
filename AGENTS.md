# AGENTS.md — Autonomous_business

Purpose
- Repo-local contract for the Kaspi operating system in this repo.
- Global/shared agent behavior lives in the control-plane docs, not here.

Start Here
- Read `docs/00_START_HERE.md`, then `.claude/OPERATING.md`, then the owning spec for the task.
- Use `.claude/GOALS.md`, `.claude/TASKS.md`, `.claude/PROGRESS.md`, `.claude/ISSUES.md`, `.claude/DECISIONS.md`, and `.claude/SESSION_LOG.md` as mutable state only.

Repo Boundaries
- Repo scope is Kaspi-only unless explicitly instructed otherwise.
- Rules/spec docs are canonical. If a formula or business rule must change, update the owning doc first, then code.
- `db/app.db` is operational truth.
- `exports/` and dashboards are derived views only.
- Excel under `excel_ui/` is UI/input contract only. XLSX changes must obey `docs/inventory/Excel_UI_Contract_for_CRM_V1.md`.

Write Safety
- Do not edit `.env` or commit secrets.
- All write scripts default to dry run.
- Apply requires an explicit write-enable env gate and `--apply`.
- Back up the DB before any apply and record the backup path in the handoff.
- No implicit DB migrations during validation.
- Parallel agents use separate git worktrees. DB-writing agents must isolate `AB_DATA_DIR` or serialize writes.
- Canonical parallel-work protocol: `.claude/PARALLEL_WORK.md`.

Cashflow Decision Gate
- Decision-grade cashflow requires:
  - ACTUAL vs MODELLED separation by statement coverage
  - `last_statement_date` plus trust banner
  - rolling 14-day Kaspi sync for every store
  - no partial-range rebuild that resets opening balances
- Owning docs/config:
  - `docs/KASPI_ORDER_CASHFLOW_TRACKING.md`
  - `docs/KASPI_API_DAILY_PIPELINE_EXEC_SUMMARY_2026-01-22.md`
  - `config/payout_model.yaml`
  - `config/bank_accounts.yaml`
  - `docs/PLAN_G40_G44_CASHFLOW_TRUSTED_DASHBOARD_V3_API_FORWARD.md` if present

Oracle + Skills
- Skills source of truth: `${ORCH_HOME:-$HOME/Docs/Oracle/agent-scripts-main}/skills`
- Home mirrors are caches: `~/.codex/skills`, `~/.claude/skills`
- Repo-local `.claude/skills` is ignored.
- Offline oracle pack: `scripts/oracle_pack.sh`
- Online oracle run: `scripts/oracle_run.sh --confirm`
- Git workflow rules live in `.claude/GIT_HYGIENE.md`

Parallel Rollout Default
- Default multi-agent mode in this repo is `one write-capable execution agent + read-only analyst agents`.
- Canonical repo protocol: `docs/PARALLEL_EXECUTION_PROTOCOL.md`
- Scaffold new runs with `python3 scripts/init_parallel_rollout.py --slug ... --purpose ...`
- Analysts publish to the out-of-repo handoff folder; only the execution agent writes shared repo state.
- DB writes remain serialized or isolated per `AB_DATA_DIR`; no concurrent DB mutation across agents.

Owning Docs
- Inventory math: `docs/inventory/Master_Inventory_Rules_v9.md`
- Data model: `docs/inventory/Sales_Data_Model_V16.md`
- PO / size allocation: `docs/protocol/active/PO_making_logic_v3.md`, `docs/size_engine_specification.md`
- FX: `docs/protocol/active/FX_RATES_MECHANISM_V1.md`
- Excel UI contract: `docs/inventory/Excel_UI_Contract_for_CRM_V1.md`
- Daily ops: `docs/DAILY_SOP.md`

Required Gates
- Default:
  - `python3 scripts/validate_params.py --strict`
  - `python3 scripts/run_end_of_day.py --verbose`
  - `pytest -q`
  - `scripts/check_no_db_tracked.sh`
- If docs touched: `scripts/lint_docs.sh`
- If cashflow touched: `python3 scripts/validate_cashflow_invariants.py`
- If PO dashboard / ordering touched: `python3 scripts/validate_po_dashboard_invariants.py`

Stopline
- Stop if any required gate fails.
- Stop if docs/specs conflict.
- Stop if formulas or business rules need to change before the owning doc is updated.
- Stop if a write path lacks explicit write-enable flags.
- Log blockers in `.claude/ISSUES.md` and `.claude/SESSION_LOG.md` before expanding scope.

Handoff
- Record evidence and command outputs in `.claude/SESSION_LOG.md`.
- Update `.claude/PROGRESS.md` with pass/fail status plus next blocker.
- Include rollback steps for git and DB restore per `.claude/GIT_HYGIENE.md`.
