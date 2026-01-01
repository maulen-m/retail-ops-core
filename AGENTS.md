# AGENTS.md — Project‑3 (Autonomous_business)

Control plane (read first):
- ${ORCH_HOME:-$HOME/Docs/Oracle/agent-scripts-main}/AGENTS.md
Skills:
- ${ORCH_HOME:-$HOME/Docs/Oracle/agent-scripts-main}/skills/oracle/SKILL.md

This file is the repo‑local contract: entrypoints, gates, and safety boundaries.

---

## What this repo is
A daily operations engine for inventory + PO autonomy:
- demand estimation + OOS logic
- safety stock / reorder math
- PO draft generation + scoring
- capital guardrails (ROIC, concentration, budget, rollout caps)
- daily pipeline orchestration (shadow → assisted → partial auto)

---

## Current high‑ROI goal
Make `python3 scripts/run_end_of_day.py --verbose` reliably run through the pipeline (or fail with a clear actionable error).
Right now, the top priority is unblocking startup/import crashes before chasing deeper logic.

---

## Non‑negotiables (capital protection)
- Atomic commits, reversible diffs, proof-of-fix required.
- Do NOT edit `.env` or secrets (human-owned).
- Do NOT weaken execution gating or guardrails defaults.
- Do NOT change canonical formulas/constants unless task explicitly targets them.
- No destructive git ops.

---

## Entrypoints (what to run)
- `python3 scripts/validate_params.py --strict`  (hard gate)
- `python3 scripts/run_end_of_day.py --verbose` (daily pipeline)
- `python3 scripts/generate_po_dashboard_data.py` (dashboard output)
- `python3 scripts/smoke_test_dashboard.py` (invariants)
- `python3 -m pytest tests/ -q` (tests; prefer targeted subsets)

---

## One‑Take autonomy envelope (wide scope, safe)
Codex can run long and chase the pipeline to green **within these boundaries**.

Allowed without asking:
- fix import crashes / missing exports / signature drift
- improve error messages + fail-fast operator guidance
- add small regression tests for touched code
- small hygiene fixes (ignore/untrack cache artifacts) in separate commit

Must HALT + ask if:
- you need to change money execution behavior, Kaspi write paths, guardrail thresholds, or core formulas
- you think a schema migration is required
- scope expands beyond ~10 files or >5 commits
- business rule ambiguity (not sure what “correct” is)

---

## Commit discipline
- Use `scripts/committer` if available.
- Keep commits atomic:
  - `alerts: fix missing exports (unblock end-of-day)`
  - `test: add regression for end-of-day import safety`
  - `ops: untrack cache artifacts (reduce drift)`

---

## Definition of Done (required)
A task is not done until:
1) Gates run + evidence captured:
   - `python3 scripts/validate_params.py --strict`
   - `python3 scripts/run_end_of_day.py --verbose`
2) Atomic commits exist.
3) Oracle pack generated to disk and path recorded.

Oracle pack:
- Prefer clean tree (reproducible). Use `--allow-dirty` only if unavoidable and explain why.
- If branch is `task/<TASK>-...`, omit `--task` (auto-detect).

Example:
`scripts/oracle_pack.sh --range HEAD~2..HEAD --cmd "python3 scripts/validate_params.py --strict" --cmd "python3 scripts/run_end_of_day.py --verbose"`

Record pack path + commit hashes in `.claude/SESSION_LOG.md`.

---

## Repo hygiene rule (stop thrashing)
Never commit:
- `.DS_Store`
- `**/__pycache__/**`, `*.pyc`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`
- `db/*.db`, `exports/*`, `excel/*`, `excel_ui/*`, `*.xlsx`, `*.pdf`, `*.zip`
If any are tracked: untrack in a dedicated commit (do NOT delete local files).
