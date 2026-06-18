Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-21_mvos_phase0_canonical_route/agent_c_report.md`

Completion requirement:

- Write the assigned closeout first.
- The closeout must include a standalone line: `Gate: <GREEN/YELLOW/RED>`.
- Do not edit repo files, `.claude/*`, DB, workbooks, scheduler files, configs, source pointers, external systems, validator exports, or generated dashboards.
- Your only write target is the assigned closeout report above.

Prepared Agent C prompt from the Human Owner / CodeCaptain packet follows.

---

You are Agent C, read-only analyst.

Phase: Phase 0 - Freeze, Canonicalize, Route
Focus: Retained blockers, source truth map, gate matrix, owner/CodeCaptain request routing.

You are read-only. You must not edit repo files. You must not edit `.claude/*`. You must not write to `db/app.db`, workbooks, scheduler files, configs, source pointers, external systems, exports used by validators, or generated dashboards. Your only write target is your closeout report in the shared handoff folder.

Repo:
`~/Docs/Autonomous_business`

Shared handoff folder:
`~/Docs/Autonomous_business_agent_handoffs/2026-05-21_mvos_phase0_canonical_route/`

Write only:
`~/Docs/Autonomous_business_agent_handoffs/2026-05-21_mvos_phase0_canonical_route/agent_c_report.md`

Read first:
1. `AGENTS.md`
2. `docs/00_START_HERE.md`
3. `.claude/OPERATING.md`
4. `docs/current/FINAL_10_OUT_OF_10_EXECUTION_PLAN.md`
5. `docs/contracts/MVOS_10_OUT_OF_10_DECISION_GRADE_ACCEPTANCE_CONTRACT.md`
6. `docs/contracts/mvos_source_contracts/ACTIVE_MVOS_SOURCE_CONTRACT_REGISTRY.json`
7. latest Agent9178 closeout and sidecar outputs
8. validator stdout files for:
   - source freshness;
   - policy gates;
   - order-entry freshness;
   - sales-vs-workbook anchor;
   - single-truth system;
   - PO money gate;
   - PO dashboard invariants;
   - copied DB manifest.

Mission:
Create an evidence-backed blocker and gate routing report. Do not repair anything. Do not try to make green. Your job is to tell the Main Orchestrator exactly what is blocking 10/10, what can be handled locally, what needs Human Owner, and what needs CodeCaptain.

Allowed read-only commands:
```bash
pwd
date
git rev-parse HEAD
git branch --show-current
git status --short
ls -la docs/contracts/mvos_source_contracts 2>/dev/null || true
ls -la exports/automation_control/2026-05-21 2>/dev/null || true
find . -path './.git' -prune -o -iname '*validate*source*freshness*stdout*' -print
find . -path './.git' -prune -o -iname '*policy_gate*stdout*' -print
find . -path './.git' -prune -o -iname '*po_money*stdout*' -print
find . -path './.git' -prune -o -iname '*single_truth*stdout*' -print
find . -path './.git' -prune -o -iname '*order_entries_freshness*stdout*' -print
find . -path './.git' -prune -o -iname '*po_dashboard*stdout*' -print
```

Do not rerun validators unless the Main Orchestrator explicitly authorizes and output is directed outside repo state. Prefer existing captured stdout/JSON sidecars.

Do not inspect Agent B's report before publishing your first-pass report.

Your report must include:

1. READCHECK
   - exact files read;
   - exact commands run;
   - no-write confirmation.

2. Current retained blocker board draft
   TSV-style rows:
   `blocker_id	severity	current_signal	business_surface_blocked	why_it_matters	next_route	owner_needed	codecaptain_needed	exit_gate`

   Include at minimum:
   - stale child sources: ads, cashflow, order entry, order status, sales, stock;
   - blocked C3 gates: ads_source_truth, cashflow_source_truth, source_freshness, stock_source_truth;
   - physical stock snapshot stale;
   - Universal/STOREB order-entry identity/freshness failure;
   - workbook content lag;
   - single-truth system/alignment failures;
   - PO money gate failures;
   - high stock retained exceptions;
   - dirty repo as production stopline;
   - automation paused boundary.

3. Source truth map draft
   TSV-style rows:
   `source_id	domain	current_status	authority_path	freshness_rule	blocks_publication	production_authority	next_action`

   Required rule:
   - Do not clear physical stock from Merchant Cabinet offer availability.
   - Do not zero missing ads spend.
   - Do not claim owner publication from copied-temp source bridge.
   - Do not use parent operational truth rollup to clear child source rows.

4. Gate matrix draft
   TSV-style rows:
   `gate_id	command	scope	expected_artifact	pass_label	fail_label	phase`

   Include gates for:
   - docs lint;
   - no DB tracked;
   - write-side gating;
   - source contract registry;
   - source freshness;
   - policy gate results;
   - order-entry freshness;
   - sales-vs-workbook anchor;
   - PO dashboard invariants;
   - single-truth system;
   - single-truth alignment;
   - PO money gate;
   - cashflow invariants;
   - copied-temp proof;
   - production preflight;
   - repeated-run;
   - scheduler heartbeat/status.

5. Human Owner request draft
   Include only requests that cannot be resolved locally.
   Required columns:
   `request_id	question	why_needed	blocked_work	priority	default_if_no_answer`

6. CodeCaptain request draft
   Include only big gates:
   - authority conflict;
   - production preflight;
   - production apply;
   - final 10/10 publication/scheduler gate;
   - capital-risk override.

7. Stoplines found
   List anything that should stop Phase 0 integration.

8. Agent C final classification
   Choose one:
   - `AGENT_C_GREEN_BLOCKER_ROUTE_READY`
   - `AGENT_C_YELLOW_BLOCKER_ROUTE_GAPS`
   - `AGENT_C_RED_AUTHORITY_CONFLICT_OR_FALSE_GREEN_RISK`

Closeout rule:
Do not say "done" unless the report file exists and contains all required sections.
