# Agentic Engineering Upgrade Plan (Steipete-inspired) — Project 3

## Goal
Increase shipping speed while reducing capital/ops risk by making agent work:
- deterministic (repeatable steps),
- low-blast-radius (small commits),
- context-efficient (agents always know “where to look”),
- evaluation-driven (every change has a fast proof).

Inspiration sources:
- https://steipete.me/posts/2025/shipping-at-inference-speed
- https://steipete.me/posts/just-talk-to-it
- https://github.com/steipete/agent-scripts
- https://gist.github.com/steipete/88a38157e8c9d1896443eca09e95e163 (committer)
- https://gist.github.com/steipete/d3b9db3fa8eb1d1a692b7656217d8655 (agent git rules)

---

## Core Principles (non-negotiable)

1) Close the loop with CLI gates
- Every meaningful change must be verified with a command that proves it works.
- Default gates for this repo:
  - python scripts/validate_params.py --strict
  - python scripts/run_end_of_day.py --verbose
  - python -m pytest tests/ -q (or targeted tests)

2) Blast radius discipline
- Keep tasks “small bombs”: aim for <5 files touched per commit when possible.
- If the agent starts editing many files, stop and re-scope.

3) Atomic commits
- One purpose per commit.
- Commit only the files you edited (explicit paths).
- Avoid committing local artifacts (.db, exports, Excel temp files).

4) One always-loaded “agent brain”
- Add a repo-root AGENTS.md that states:
  - current state,
  - entry points,
  - non-negotiables,
  - quick doc map,
  - standard commands,
  - prompt templates.

5) Context packs only when needed
- For review/planning: provide a small context bundle (changed files + relevant docs).
- Avoid dumping full-repo packs unless doing deep refactors.

---

## Phase 0 — Quick Wins (≤1 day)

### 0.1 Add AGENTS.md (Codex-optimized)
Benefit: faster onboarding per session, fewer hallucinated paths, fewer “I couldn’t find CLAUDE.md.”
Effort: S
Risk: Low

### 0.2 Add scripts/committer
Benefit: prevents accidental commits of junk; makes “atomic commits” easy for non-coders.
Effort: S
Risk: Low

### 0.3 Add/extend .gitignore for local artifacts
Benefit: drastically reduces git noise + accidental commits (db/app.db, exports/*.csv, Excel temp, .DS_Store).
Effort: S
Risk: Low

### 0.4 Fix “green loop blocker”: log_audit ImportError
Benefit: unblocks full end-of-day pipeline; enables daily validation and “shipping factory” loops.
Effort: S/M
Risk: Medium (touches ingest + ledger; must add tests)

---

## Phase 1 — Workflow Refactor (1–3 days)

### 1.1 Standardize “task handoff format”
- Create a single canonical prompt template for implementation agents.
- Include: goal, constraints, files to touch, gates to run, “done means” checks.

### 1.2 Add a lightweight Docs Index (inside AGENTS.md)
- Add a 15-line index of “read_when” rules:
  - when editing inventory math → read Master_Inventory_Rules_v6.md
  - when editing PO logic → read PO_making_logic_v2.md
  - when editing daily ops → read docs/DAILY_SOP.md
  - when editing schema/params → read docs/protocol/FX_RATES_MECHANISM_V1.md
This is the low-effort version of a docs-list script.

### 1.3 Add a single “Gate Script”
- A convenience runner (bash or python) that runs:
  - validate_params --strict
  - a targeted test subset
  - smoke test
- Makes it easier for the human bridge to validate without remembering steps.

---

## Phase 2 — Deeper Automation / Eval Harness (3–14 days)

### 2.1 Add CI (GitHub Actions) for tests + sanity gates
Benefit: fewer regressions, easier merges, faster review.
Effort: M
Risk: Medium (CI may reveal hidden nondeterminism; good to fix)

### 2.2 Add “shadow scorecard regression gate”
- Compare daily scorecard metrics vs trailing 7-day average.
- If drift exceeds thresholds, mark run as WARN (not FAIL).

### 2.3 Weekly refactor day checklist
- Duplicate detection, dead code checks, doc updates, slow-test cleanup.
- Keep the codebase “agent-friendly” long-term.

---

## Stop Doing / Start Doing / Keep Doing

Stop doing:
- Huge multi-file changes in one commit.
- Full-repo context dumps for small changes.
- Running pipelines without capturing stdout/stderr evidence.

Start doing:
- Commit with explicit file lists (use scripts/committer).
- Use “blast radius” checkpoints: if it expands, stop.
- Provide changed-files-only context packs for Code Captain review.

Keep doing:
- Fail-fast validation (validate_params --strict).
- Strong unit tests + invariants for PO logic.
- Shadow-mode scoring and operational runbooks.

---

## Success Criteria

Within 7 days:
- End-of-day pipeline runs to completion (or fails with actionable errors) every day.
- Any code change lands as 1–3 atomic commits.
- Agents can start a new session and orient in <2 minutes using AGENTS.md.
