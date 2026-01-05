# AGENTS.md - Project 3 (Autonomous Inventory/PO System)

Read `docs/00_START_HERE.md` before anything else.

Read orchestrator rules first:

- ORCHESTRATOR: `AGENTS.md` in the control plane (agent-scripts-main)

This file is the **local contract**: product goals + stack + gates.

---

Purpose: single always-loaded brain for Codex/agents. Keep it short, factual, and operational.

---

## Current State (update weekly)
- End-of-day pipeline: Step 0-1 OK; Step 2 depends on core/db/ledger.log_audit + fact_input_audit table.
- Automation mode: shadow mode + guardrails exist; execution is gated behind env flags.
- Capital safety: guardrails enforced (ROIC gate, concentration, budget caps, rollout caps).
- Known optional warning: dim_budget_caps may be missing/unlimited depending on setup.

---

## Non-Negotiables
- DO NOT edit `.env` or any secrets files. Only the human changes env vars.
- No destructive git ops unless explicitly instructed (no `git reset --hard`, no nuking files to "fix tests").
- No implicit DB migrations in validation; use explicit migration scripts.
- Keep commits atomic. Commit only files you touched.
- Protect capital first: never weaken guardrails.

---

## Repo Entry Points (start here)
- scripts/run_end_of_day.py       -> daily pipeline (steps 0-7)
- scripts/validate_params.py      -> strict parameter validation gate
- scripts/smoke_test_dashboard.py -> invariants gate
- scripts/generate_po_dashboard_data.py -> dashboard JSON generation

---

## Docs: ALWAYS read this first
1) **docs/00_START_HERE.md**  
This file contains the “source-of-truth ladder” and the minimum reading set per task.  
Do not load the whole docs folder by default.

---

## Docs Index (read_when rules)
- If editing inventory formulas / parameters -> docs/inventory/Master_Inventory_Rules_v8.md
- If editing PO logic / size allocation -> docs/protocol/active/PO_making_logic_v2.md + docs/size_engine_specification.md
- If editing FX rates or payments assumptions -> docs/protocol/active/FX_RATES_MECHANISM_V1.md
- If editing daily ops pipeline -> docs/DAILY_SOP.md
- If editing schema -> db/schema.sql + scripts/validate_params.py + docs/inventory/Sales_Data_Model_V16.md

---

## Workflow Principles (Steipete-inspired)
- Keep blast radius small (target: <=5 files per commit).
- Prefer CLI-first changes and close the loop with gates.
- Ask for options/status before big changes.
- Use tight context packs for reviews (changed files + key docs).
- Keep prompts short and direct; queue follow-ups instead of huge plans.

---

## Default "Green Loop" Commands
1) python3 scripts/validate_params.py --strict
2) python3 scripts/run_end_of_day.py --verbose
3) python3 -m pytest tests/ -q (or targeted tests)

---

## Guardrail Checks
- scripts/lint_docs.sh
- scripts/check_no_db_tracked.sh

---

## Commit Helper
Use scripts/committer to avoid staging junk:
- scripts/committer "TASK-XXX: short message" path/to/file1 path/to/file2

---

## Oracle Pack (definition of done)
- After each task, generate an oracle pack to disk for review:
  - scripts/oracle_pack.sh --task TASK-XXX --range HEAD~1..HEAD --cmd "pytest -q" --cmd "python3 scripts/run_end_of_day.py --verbose"
- Link the generated `~/Docs/Oracle/...` path in the session log/handoff.
- Prefer a clean working tree; only use `--allow-dirty` when reproducibility is not possible.
- You can omit `--task` if the branch is named `task/<TASK>-...`.

---

## Blast Radius Rule (important)
Before coding:
- Estimate files touched (target: <=5)
- If it grows: stop, explain why, re-scope.

---

## Prompt Templates

### Template A - Implementation Task (to Codex/Opus)
- Goal:
- Constraints (idempotent, no .env changes, no destructive git):
- Files allowed to touch:
- Tests/gates to run:
- Done means checklist:


### Template B - Review Request (to Code Captain)
- Context pack: oracle render output or changed-files-only bundle.
- Path to oracle docs: "~/Docs/steipete/oracle-main"
- What changed + why:
- Evidence: command outputs + commit hash
- Risks/rollbacks:

### Template C - Status/Options Ping
- Status check:
- What is blocked or unclear:
- Provide 2-3 options before changing code.
