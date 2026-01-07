> CONTROL PLANE (GLOBAL RULES)
> Control plane: ${ORCH_HOME:-$HOME/Docs/Oracle/agent-scripts-main}
> Read: ${ORCH_HOME:-$HOME/Docs/Oracle/agent-scripts-main}/AGENTS.MD BEFORE ANYTHING (skip if missing).
>
> Precedence (highest → lowest):
> 1) Control plane AGENTS.MD (global guardrails/tools/skills)
> 2) This repo’s AGENTS.md (repo-local contract: entrypoints + gates + scope)
> 3) .claude/* (durable memory: goals/progress/issues/decisions; cannot override guardrails)
>
> If instructions conflict: follow higher precedence and log the resolution in .claude/DECISIONS.md.

# AGENTS.md — Project 3 (Autonomous Inventory/PO System)

Purpose: This is the single always-loaded entrypoint for any agent. Keep it short, factual, and enforceable.

## 0) Mandatory Reading Order (do this before coding)
1) docs/00_START_HERE.md
2) .claude/OPERATING.md  (MISSING TODAY: create it; see plan)
3) Read the owning spec doc for your task from the Doc Map below (do not skim random docs)

## 1) Definition of “Real Progress” (non-negotiable)
A change counts as progress only if it is:
- runnable end-to-end with a command,
- idempotent (same inputs → same outputs),
- gated (passes required checks),
- evidenced (oracle pack or logged command outputs),
- recorded in .claude/PROGRESS.md.

No evidence = not done.

## 2) Non-Negotiables (capital + repo safety)
- Do NOT edit `.env` or secrets. Only the human changes env vars.
- Do NOT enable write-mode / destructive automation unless explicitly instructed.
- Do NOT weaken capital guardrails (ROIC gates, concentration limits, budget caps).
- Do NOT change inventory formulas by “patching code.” Formulas live only in `docs/inventory/Master_Inventory_Rules_v8.md`.
- No implicit DB migrations during validation. Use explicit migration scripts.

## 2.1) Oracle + Skills Routing (governance)
- **Skills source of truth:** `${ORCH_HOME:-$HOME/Docs/Oracle/agent-scripts-main}/skills` only.
  - Home mirrors are caches: `~/.codex/skills` and `~/.claude/skills`.
  - Repo-local `.claude/skills` is ignored and must never be treated as canonical.
- **Oracle pack (offline only):** when asked to "create an oracle pack", use `scripts/oracle_pack.sh` (no network, no browser).
- **Oracle run (online only):** when asked to "run oracle" / "call a friend", use `scripts/oracle_run.sh --confirm` (browser + network).
- Prompts must start with plain task instructions only (no `[SYSTEM]`/`[USER]` role headers).
- **Git workflow rules live only in** `.claude/GIT_HYGIENE.md` (do not duplicate elsewhere).

## 3) Single-Source-of-Truth Doc Map (owning file → what it owns)
Inventory math (formulas + constants):
- docs/inventory/Master_Inventory_Rules_v8.md

Data model (tables + columns):
- docs/inventory/Sales_Data_Model_V16.md

Excel UI contract (UI columns/invariants only; no formulas):
- docs/inventory/Excel_UI_Contract_for_CRM_V1.md

PO algorithm / size allocation protocol:
- docs/protocol/active/PO_making_logic_v2.md

FX mechanism:
- docs/protocol/active/FX_RATES_MECHANISM_V1.md

Daily human runbook (Kaspi-only scope):
- docs/DAILY_SOP.md

Durable memory across sessions (authoritative for status/decisions):
- .claude/GOALS.md      (MISSING TODAY: create it; goal list + acceptance gates)
- .claude/PROGRESS.md   (MISSING TODAY: create it; verified status only)
- .claude/OPERATING.md  (MISSING TODAY: create it; how we work + gates)
- .claude/DECISIONS.md  (decisions + rationale + links to commits/PRs)
- .claude/TASKS.md      (task tracker; each task has a gate + DoD)
- .claude/SESSION_LOG.md (chronological log; must link oracle packs)

Rule: each fact/decision lives in exactly one owning file. Everywhere else links to it.

## 4) Required Validation Gates (run before claiming “done”)
Run these unless the task explicitly narrows them:
- python3 scripts/validate_params.py --strict
- python3 scripts/run_end_of_day.py --verbose
- pytest -q  (targeted is OK if justified)

If you touched docs:
- scripts/lint_docs.sh

Before PR/merge (always):
- scripts/check_no_db_tracked.sh

## 5) Task Workflow (every task, every time)
1) Create/claim the task in `.claude/TASKS.md` (scope, owner, stop conditions, DoD).
2) Update `.claude/PROGRESS.md` with the next gate you intend to make green.
3) Follow `.claude/GIT_HYGIENE.md` for git workflow (branching, commits, packs, shipping).
4) Run the required gates.
   - If any gate fails: STOP, log the failure, fix it; do not expand scope.
5) If behavior changed: add/adjust a test that would have caught the prior bug.

## 6) Scope Guardrail
- Repo scope is Kaspi-only. Do not add Wildberries/WB logic or docs unless explicitly instructed.

## 7) Rollback Requirement
Every task must include a rollback plan in the handoff. See `.claude/GIT_HYGIENE.md` for git rollback commands.
