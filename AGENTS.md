> CONTROL PLANE (GLOBAL RULES)
> Control plane: ${ORCH_HOME:-$HOME/Docs/Oracle/agent-scripts-main}
AGENTS_VERSION: 2026-01-27
> Read: ${ORCH_HOME:-$HOME/Docs/Oracle/agent-scripts-main}/AGENTS.MD BEFORE ANYTHING (skip if missing).
>
> Precedence (highest → lowest):
> 1) Control plane AGENTS.MD (global guardrails/tools/skills)
> 2) This repo’s AGENTS.md (repo-local contract: entrypoints + gates + scope)
> 3) .claude/* (durable memory: goals/progress/issues/decisions; cannot override guardrails)
>
> If instructions conflict: follow higher precedence and log the resolution in .claude/DECISIONS.md.


# AGENTS.md — Autonomous_business (Kaspi) — Inventory + PO + Cashflow

Purpose: single always-loaded entrypoint for any agent working in this repo.
Goal: maximize profit growth while protecting capital (cash survivability + correctness). Prefer links to owning docs over duplication.

## 0) Mandatory reading order (before coding)
### REQUIRED: READCHECK handshake (first assistant message)
Before any code changes, the agent must output a READCHECK block (in chat) and log it to `.claude/SESSION_LOG.md`:

READCHECK:
- control-plane AGENTS.MD: READ | MISSING
- repo AGENTS.md: READ
- CLAUDE.md (if present): READ
- docs/00_START_HERE.md: READ
- .claude/OPERATING.md: READ
- .claude/GOALS.md + .claude/TASKS.md: READ
- owning spec(s) for this task: <list exact paths>
- planned verification gates: <list commands>
- assumptions (if any): <bullets; if none, say NONE>

If READCHECK cannot be completed (missing files / contradictions / unclear scope): STOP and ask.

0) CLAUDE.md (if present; behavioral guardrails)
1) docs/00_START_HERE.md
2) .claude/OPERATING.md (how we work + gates + evidence protocol)
3) Check .claude/GOALS.md + .claude/TASKS.md (current phase, stop conditions, what “DONE” means)
4) Read the owning spec doc for your task from the Doc Map below (do not skim random docs)

If any file above is missing: create a minimal stub (title + purpose + pointers), commit it, and log in .claude/SESSION_LOG.md.

## 1) Definition of “Real Progress” (non-negotiable)
A change counts as progress only if it is:
- runnable end-to-end with a command,
- idempotent (same inputs → same outputs),
- gated (passes required checks),
- evidenced (oracle pack and/or logged outputs),
- recorded in .claude/PROGRESS.md.

No evidence = not done.

WHY: this system controls capital decisions; “looks correct” is not acceptable without reproducible proof.

## 2) Source-of-truth hierarchy (do not mix)
- Rules/spec docs are canonical (see Doc Map). If a formula/spec must change: update owning doc first, then implement code.
- DB (db/app.db) is the operational truth for facts/dims/snapshots/anchors.
- exports/ and dashboards are derived views of DB outputs (never recompute business math in browser JS).
- Excel under excel_ui/ is UI/contracts or input sources only. If generating/modifying XLSX, obey docs/inventory/Excel_UI_Contract_for_CRM_V1.md (Mac Excel safety).

## 3) Non-negotiables (repo safety + capital safety)
- Do NOT edit `.env` or commit secrets. Only the human changes env vars.
- All write scripts must default to DRY RUN.
  - Apply requires explicit env flag (e.g., ENABLE_*_WRITE=1) AND `--apply`.
  - Always DB-backup BEFORE any apply; record backup path in the handoff/oracle pack.
- No implicit DB migrations during validation. Use explicit migration scripts.
- Parallel work must use separate git worktrees.
  - Never run two DB-writing agents against the same db/app.db unless AB_DATA_DIR is isolated per worktree.
  - Canonical protocol: .claude/PARALLEL_WORK.md
- If a gate fails: STOP. Log to .claude/ISSUES.md + .claude/SESSION_LOG.md. Fix without expanding scope.
- Any painful bug discovery must become an invariant/test so it never returns.

## 4) Cashflow operating contract (minimum invariants)
Cashflow is “decision-grade” only when:
- Days backed by MT940 statements are labeled ACTUAL; forward days are MODELLED unless balance-check events exist.
- Dashboard must show last_statement_date + trust banner.
- Kaspi Orders API has a 14-day lookback → rolling daily 14-day sync is mandatory.
  - If any store sync is stale, cashflow is NOT decision-grade (default: fail gate unless explicit override + logged reason).
- Never allow partial-range rebuilds to overwrite daily tables in a way that resets opening balances.

Canonical docs/configs (do not reinterpret rules):
- docs/KASPI_ORDER_CASHFLOW_TRACKING.md
- docs/KASPI_API_DAILY_PIPELINE_EXEC_SUMMARY_2026-01-22.md
- config/payout_model.yaml
- config/bank_accounts.yaml
- (If present) docs/PLAN_G40_G44_CASHFLOW_TRUSTED_DASHBOARD_V3_API_FORWARD.md

## 5) Oracle + skills routing (governance)
- Skills source of truth: `${ORCH_HOME:-$HOME/Docs/Oracle/agent-scripts-main}/skills` only.
  - Home mirrors are caches: `~/.codex/skills` and `~/.claude/skills`.
  - Repo-local `.claude/skills` is ignored.
- Oracle pack (offline only): use `scripts/oracle_pack.sh` (no network).
- Oracle run (online only): use `scripts/oracle_run.sh --confirm` (browser + network).
- Git workflow rules live only in `.claude/GIT_HYGIENE.md` (do not duplicate elsewhere).

## 6) Single-source-of-truth Doc Map (minimal, high-signal)
Inventory math (formulas + constants):
- docs/inventory/Master_Inventory_Rules_v8.md

Data model (tables + columns):
- docs/inventory/Sales_Data_Model_V16.md

PO algorithm / size allocation protocol:
- docs/protocol/active/PO_making_logic_v2.md
- docs/size_engine_specification.md (size canonicalization rules)

FX mechanism:
- docs/protocol/active/FX_RATES_MECHANISM_V1.md

Excel UI contract (invariants + Mac Excel safety):
- docs/inventory/Excel_UI_Contract_for_CRM_V1.md

Daily ops:
- docs/DAILY_SOP.md

## 7) Required validation gates (run before claiming “done”)
Default (unless task explicitly narrows scope):
- python3 scripts/validate_params.py --strict
- python3 scripts/run_end_of_day.py --verbose
- pytest -q
- scripts/check_no_db_tracked.sh

If docs touched:
- scripts/lint_docs.sh

If cashflow touched:
- python3 scripts/validate_cashflow_invariants.py

If PO dashboard / ordering touched:
- python3 scripts/validate_po_dashboard_invariants.py

## 8) Task workflow (every task, every time)
1) Create/claim the task in .claude/TASKS.md (scope, owner, stop conditions, DoD).
2) Update .claude/PROGRESS.md with the next gate you intend to make green.
3) Follow .claude/GIT_HYGIENE.md for branching/commits/packs/shipping.
4) Execute in atomic commits (one intent per commit).
5) Run required gates.
6) Produce oracle pack + concise status log; record in .claude/SESSION_LOG.md.

## 9) Scope guardrail
- Repo scope is Kaspi-only unless explicitly instructed otherwise.

## 10) Rollback requirement
Every task handoff must include rollback steps (git + DB restore) per .claude/GIT_HYGIENE.md.
