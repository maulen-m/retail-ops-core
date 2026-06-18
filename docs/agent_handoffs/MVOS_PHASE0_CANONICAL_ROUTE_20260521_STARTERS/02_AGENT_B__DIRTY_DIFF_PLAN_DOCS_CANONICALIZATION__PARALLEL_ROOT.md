Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-21_mvos_phase0_canonical_route/agent_b_report.md`

Completion requirement:

- Write the assigned closeout first.
- The closeout must include a standalone line: `Gate: <GREEN/YELLOW/RED>`.
- Do not edit repo files, `.claude/*`, DB, workbooks, scheduler files, configs, source pointers, external systems, validator exports, or generated dashboards.
- Your only write target is the assigned closeout report above.

Prepared Agent B prompt from the Human Owner / CodeCaptain packet follows.

---

You are Agent B, read-only analyst.

Phase: Phase 0 - Freeze, Canonicalize, Route
Focus: Dirty repo grouping, plan sprawl inventory, docs/current canonicalization recommendations.

You are read-only. You must not edit repo files. You must not edit `.claude/*`. You must not write to `db/app.db`, workbooks, scheduler files, configs, source pointers, external systems, exports used by validators, or generated dashboards. Your only write target is your closeout report in the shared handoff folder.

Repo:
`~/Docs/Autonomous_business`

Shared handoff folder:
`~/Docs/Autonomous_business_agent_handoffs/2026-05-21_mvos_phase0_canonical_route/`

Write only:
`~/Docs/Autonomous_business_agent_handoffs/2026-05-21_mvos_phase0_canonical_route/agent_b_report.md`

Read first:
1. `AGENTS.md`
2. `docs/00_START_HERE.md`
3. `.claude/OPERATING.md`
4. `docs/current/FINAL_10_OUT_OF_10_EXECUTION_PLAN.md`
5. `docs/PARALLEL_EXECUTION_PROTOCOL.md`
6. `docs/WRITE_SIDE_GATING_CONTRACT.md`
7. `docs/WRITE_APPLY_RUNBOOK.md`

Mission:
Create an evidence-backed report that lets the Main Orchestrator clean the plan/docs/repo structure without losing history or touching production.

Allowed read-only commands:
```bash
pwd
date
git rev-parse HEAD
git branch --show-current
git status --short
git diff --name-only
git diff --stat
find docs -maxdepth 2 -iname 'PLAN*.md' -print
find docs/parallel_runs -maxdepth 2 -name 'PLAN.md' -print
find docs/agent_handoffs -maxdepth 2 -type d -print
find docs/current -maxdepth 1 -type f -print 2>/dev/null || true
```

Do not run commands that write outputs into repo state.
Do not run broad tests unless explicitly read-only and output is redirected to your handoff report.
Do not inspect Agent C's report before publishing your first-pass report.

Your report must include:

1. READCHECK
   - exact files read;
   - exact commands run;
   - no-write confirmation.

2. Dirty repo grouping
   For every modified/untracked path visible from `git status --short`, classify:
   - path;
   - git status;
   - category;
   - risk;
   - recommended action.

   Use categories:
   - CURRENT_DOCS_TO_CREATE_OR_KEEP
   - AUTHORITY_DOC_OR_CONTRACT
   - VALIDATOR_OR_TEST
   - SOURCE_MATERIALIZER_OR_IMPORT
   - CONFIG_OR_WRITE_BOUNDARY
   - MUTABLE_CLAUDE_LOG
   - HANDOFF_HISTORY
   - PARALLEL_RUN_HISTORY
   - GENERATED_OR_DERIVED_OUTPUT
   - IMPORT_DATA
   - NEEDS_ORCHESTRATOR_REVIEW

   Recommended actions:
   - KEEP_ACTIVE
   - MERGE_INTO_DOCS_CURRENT
   - SUPERSEDE_AND_ARCHIVE
   - PARK_UNTIL_PHASE1
   - COMMIT_AS_LOGICAL_BATCH
   - REVIEW_BEFORE_COMMIT
   - DO_NOT_DELETE_YET

3. Plan sprawl inventory
   - count shallow `docs/PLAN*.md`;
   - count `docs/parallel_runs/*/PLAN.md`;
   - list top candidate files/folders to supersede;
   - recommend archive location;
   - do not recommend deletion unless clearly generated duplicate output and safe.

4. Canonical docs/current recommendation
   Confirm the exact files that should exist:
   - `FINAL_10_OUT_OF_10_EXECUTION_PLAN.md`
   - `CURRENT_AUTHORITY_INDEX.md`
   - `CURRENT_ARCHITECTURE_MAP.md`
   - `CURRENT_SOURCE_TRUTH_MAP.md`
   - `CURRENT_BLOCKER_BOARD.tsv`
   - `CURRENT_GATE_MATRIX.tsv`
   - `CURRENT_AGENT_OPERATING_CONTRACT.md`
   - `CURRENT_PRODUCTION_WRITE_BOUNDARY.md`
   - `SUPERSEDED_PLAN_INDEX.tsv`

5. Supersession map draft
   Provide TSV-style rows:
   `path	status	recommended_action	superseded_by	notes`

6. Stoplines found
   List anything that should stop Phase 0 integration.

7. Agent B final classification
   Choose one:
   - `AGENT_B_GREEN_DOC_ROUTE_READY`
   - `AGENT_B_YELLOW_DOC_ROUTE_GAPS`
   - `AGENT_B_RED_AUTHORITY_CONFLICT_OR_WRITE_RISK`

Closeout rule:
Do not say "done" unless the report file exists and contains all required sections.
