> CONTROL PLANE (GLOBAL RULES)
> Control plane: ${ORCH_HOME:-$HOME/Docs/Oracle/agent-scripts-main}
> Read: ${ORCH_HOME:-$HOME/Docs/Oracle/agent-scripts-main}/AGENTS.MD 
BEFORE ANYTHING (skip if missing).
>
> Precedence (highest → lowest):
> 1) Control plane AGENTS.MD (global guardrails/tools/skills)
> 2) This repo’s AGENTS.md (repo-local contract: entrypoints + gates 
+ scope)
> 3) .claude/* (durable memory: goals/progress/issues/decisions; 
cannot override guardrails)
>
> If instructions conflict: follow higher precedence and log the 
resolution in .claude/DECISIONS.md.

# AGENTS.md — Autonomous_business (Kaspi) — Inventory + PO + Cashflow

Purpose: This is the single always-loaded entrypoint for any agent 
working in this repo.
Keep it short, factual, enforceable. Prefer linking to owning docs 
over duplicating details.

## 0) Mandatory reading order (before coding)
1) docs/00_START_HERE.md
2) .claude/OPERATING.md
3) Read the owning spec doc for your task from the Doc Map below (do 
not skim random docs)
4) Check .claude/GOALS.md + .claude/TASKS.md for current phase + stop 
conditions

## 1) Definition of “Real Progress” (non-negotiable)
A change counts as progress only if it is:
- runnable end-to-end with a command,
- idempotent (same inputs → same outputs),
- gated (passes required checks),
- evidenced (oracle pack and/or logged outputs),
- recorded in .claude/PROGRESS.md.

No evidence = not done.

WHY: this system controls capital decisions; “looks correct” is not 
acceptable without reproducible proof.

## 2) Source-of-truth hierarchy (do not mix)
- **Rules/spec docs are canonical** (see Doc Map). If a *formula/
spec* must change: update the owning doc first, then implement code.
- **DB (db/app.db) is the operational truth** for facts/dims/
snapshots/anchors.
- **exports/** and dashboards are derived views of DB outputs (never 
recompute business math in browser JS).
- **Excel files under excel_ui/** are UI/contracts or input sources 
only. If generating/modifying XLSX, obey docs/inventory/
Excel_UI_Contract_for_CRM_V1.md (Mac Excel safety).

## 3) Non-negotiables (repo safety + capital safety)
- Do NOT edit `.env` or commit secrets. Only the human changes env 
vars.
- All write scripts must default to DRY RUN.
  - Apply requires explicit env flag (e.g., ENABLE_*_WRITE=1) AND 
  `--apply`.
  - Always DB-backup BEFORE any apply and record the backup path in 
  the handoff/oracle pack.
- No implicit DB migrations during validation. Use explicit migration 
scripts.
- Parallel work must use separate git worktrees. Never run two 
DB-writing agents against the same db/app.db.
  - See: .claude/PARALLEL_AGENTS.md and .claude/GIT_HYGIENE.md.
- If a gate fails: STOP. Log the failure to .claude/ISSUES.md and .
claude/SESSION_LOG.md. Fix without expanding scope.

## 4) Cashflow operating contract (minimum invariants)
Cashflow is “decision-grade” only when:
- Days backed by MT940 statements are labeled **ACTUAL**; forward 
days are **MODELLED** unless balance-check events exist.
- Dashboard must show `last_statement_date` + trust banner.
- Kaspi Orders API has a 14-day lookback → rolling daily 14-day sync 
is mandatory.
  - If any store sync is stale, cashflow is NOT decision-grade (fail 
  gate unless explicit override + logged reason).
- Never allow partial-range rebuilds to overwrite daily tables in a 
way that resets opening balances.

Canonical docs/configs (do not reinterpret rules):
- docs/KASPI_ORDER_CASHFLOW_TRACKING.md
- docs/KASPI_API_DAILY_PIPELINE_EXEC_SUMMARY_2026-01-22.md (pipeline 
overview)
- config/payout_model.yaml
- config/bank_accounts.yaml

## 5) Oracle + skills routing (governance)
- Skills source of truth: `${ORCH_HOME:-$HOME/Docs/Oracle/
agent-scripts-main}/skills` only.
  - Home mirrors are caches: `~/.codex/skills` and `~/.claude/skills`.
  - Repo-local `.claude/skills` is ignored.
- Oracle pack (offline only): use `scripts/oracle_pack.sh` (no 
network).
- Oracle run (online only): use `scripts/oracle_run.sh --confirm`.
- Git workflow rules live only in `.claude/GIT_HYGIENE.md` (do not 
duplicate elsewhere).

## 6) Single-source-of-truth Doc Map (owning file → what it owns)
Inventory math (formulas + constants):
- docs/inventory/Master_Inventory_Rules_v8.md

Data model (tables + columns):
- docs/inventory/Sales_Data_Model_V16.md

Excel UI contract (UI columns/invariants; Excel safety constraints):
- docs/inventory/Excel_UI_Contract_for_CRM_V1.md

PO algorithm / size allocation protocol:
- docs/protocol/active/PO_making_logic_v2.md

FX mechanism:
- docs/protocol/active/FX_RATES_MECHANISM_V1.md

Daily human runbook:
- docs/DAILY_SOP.md

Kaspi order economics + refunds + status mapping:
- docs/KASPI_ORDER_CASHFLOW_TRACKING.md

Durable memory across sessions:
- .claude/GOALS.md
- .claude/TASKS.md
- .claude/PROGRESS.md
- .claude/DECISIONS.md
- .claude/ISSUES.md
- .claude/SESSION_LOG.md

Rule: each fact/decision lives in exactly one owning file. Everywhere 
else links to it.

## 7) Required validation gates (run before claiming “done”)
Run these unless the task explicitly narrows them:
- python3 scripts/validate_params.py --strict
- python3 scripts/run_end_of_day.py --verbose
- pytest -q  (targeted subset OK only if justified + recorded)

If you touched docs:
- scripts/lint_docs.sh

Before PR/merge/push (always):
- scripts/check_no_db_tracked.sh

## 8) Task workflow (every task)
1) Create/claim the task in `.claude/TASKS.md` (scope, owner, stop 
conditions, DoD + gates).
2) Update `.claude/PROGRESS.md` with the next gate you intend to make 
green.
3) Follow `.claude/GIT_HYGIENE.md` for branching/commits/packs/
shipping.
4) Run the required gates.
   - If any gate fails: STOP, log, fix; do not expand scope.
5) If behavior changed: add/adjust a test or invariant that would 
have caught the prior bug.

## 9) Scope guardrail
- Repo scope is Kaspi-only unless explicitly instructed otherwise.

## 10) Rollback requirement
Every task handoff must include a rollback plan (commands + which 
commit range to revert).
See `.claude/GIT_HYGIENE.md`.