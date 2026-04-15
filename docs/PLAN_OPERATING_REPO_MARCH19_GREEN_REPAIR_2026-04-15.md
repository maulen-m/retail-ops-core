PLAN_OPERATING_REPO_MARCH19_GREEN_REPAIR_2026-04-15

Purpose

Restore the operating repo at `~/Docs/Autonomous_business` to a historically green, owner-decision-ready state for `as_of=2026-03-19`, matching the known-green retained worktree at `~/Docs/wt_webui_owner_truth_operationalization_v1`, without hiding provenance, weakening gates, or performing speculative DB surgery.

Why this exists now

The operating repo already has the replay/helper code restored, but it is still red for March 19 because the repo-state is incomplete and diverged from the green worktree:

- missing proof packages under `exports/validation/...`
- stale OPEX replay artifact in `config/opex/opex_schedule.yaml`
- `db/app.db` divergence that still fails `validate_params --strict --as-of 2026-03-19`

The current gap report is:

- `exports/validation/replay_repair/2026-03-19/operating_vs_green_gap_report.md`
- `exports/validation/replay_repair/2026-03-19/operating_vs_green_gap_manifest.json`

Execution posture

- one write-capable execution agent only
- at most two read-only analyst agents in parallel
- fail-closed
- no hidden source swaps
- no DB mutation until proof-surface and OPEX recovery are complete and replay is rerun
- every owner domain must keep provenance explicit

Recommendation

Use three agents total:

- Agent A: executor / scribe / only writer
- Agent B: proof-artifact + OPEX provenance analyst, read-only
- Agent C: DB divergence analyst, read-only

If coordination risk feels too high, fall back to a single-agent execution. That is slower, but safest.

Safe delegation boundaries

Safe to delegate in parallel:

- read-only diff of operating repo vs green worktree
- OPEX source and freshness analysis
- read-only DB divergence analysis
- read-only review of CRM workbook, archive-order API artifacts, ActiveOrders artifacts, and validation outputs

Not safe to parallelize:

- editing `db/app.db`
- regenerating shared files under `exports/validation/`
- editing `config/opex/opex_schedule.yaml`
- rerunning strict replay pipelines in the same repo checkout
- updating `.claude/SESSION_LOG.md` or `.claude/PROGRESS.md`

Worktree policy

The repo-local protocol in `.claude/PARALLEL_WORK.md` still applies.

- Agent A may work directly in `~/Docs/Autonomous_business`.
- Agents B and C should use separate read-only worktrees if they are run as true parallel coding agents.
- Only Agent A may write shared repo state.
- If DB mutation becomes necessary, Agent A must serialize all writes and record backup paths.
- Shared cross-agent handoff folder for this plan:
  - `~/Docs/Autonomous_business_agent_handoffs/2026-04-15_march19_green_repair`
  - Agents B and C may write reports there.
  - Agent A may read from there and may write its execution log there.
  - Agents B and C should not read each other's reports before publishing their own first-pass findings unless Agent A explicitly requests a second-pass cross-review.

Canonical references for this plan

Repo rules:

- `AGENTS.md`
- `docs/00_START_HERE.md`

Current stopline package:

- `exports/validation/replay_repair/2026-03-19/operating_vs_green_gap_report.md`
- `exports/diagnostics/2026-03-19/system_health.json`
- `exports/owner_pnl/2026-03-19/OWNER_PNL.json`

Known-green reference worktree:

- `~/Docs/wt_webui_owner_truth_operationalization_v1`

Useful external context:

- `~/Documents/useful tables/Main crm spreadsheets/main tables/Purchase_orders/Finance/Loans_Master_V4.1_GPT.xlsx`
  - sheet: `OPEX_SCHEDULE`
- CRM workbook and archive-order / waybill artifacts when they materially help chronology or provenance decisions
- archive-order API sales data that captures real end-state timing

Global non-negotiables

- Do not weaken a validator to make March green.
- Do not silently replace a source workbook or snapshot.
- Do not infer business truth from mutable `.claude/*.md` files.
- Do not mutate `db/app.db` before proof-artifact and OPEX repair is complete and replay has been rerun.
- Do not allow analyst agents to write repo state.
- Do not hide provenance. Every restored or regenerated owner-domain artifact must be traceable back to an explicit input and decision.

Success criteria

The plan is complete only when all of the following are true in the operating repo:

- `python3 scripts/validate_params.py --strict --as-of 2026-03-19` passes
- `./.venv/bin/python scripts/run_owner_truth_daily.py --mode replay --as-of 2026-03-19 --strict` passes
- `./.venv/bin/python scripts/system_doctor.py --strict --project-root . --as-of 2026-03-19 --runtime-mode replay --truth-source webui_archive` is green
- `exports/owner_pnl/2026-03-19/OWNER_PNL.json` is `PASS`
- the March proof packages exist with explicit provenance
- if DB was touched, backup, write gate, before/after evidence, and rollback steps are recorded

Current blocker set

From the current gap report:

1. Missing proof surface:
   - `exports/validation/webui_archive_single_truth/2026-03-19`
   - `exports/validation/identity_stabilization/2026-03-09`
   - `exports/validation/board_v8_runtime/2026-03-19`
2. OPEX replay freshness gap:
   - `config/opex/opex_schedule.yaml` is stale relative to the green worktree
3. DB divergence:
   - `validate_params --strict --as-of 2026-03-19` fails on `on_delivery_freeze` in the operating repo but passes in the green worktree

Execution order

Upstream truth blockers must clear before downstream publication:

1. confirm baseline red state
2. recover missing proof packages
3. resolve OPEX provenance and refresh the replay artifact
4. rerun replay gates
5. only then decide whether DB repair is still required
6. if DB repair is required, do it write-gated with backup-first discipline
7. rerun all target gates
8. close out with explicit provenance and rollback notes

Phase R0 — Baseline Freeze

Goal

Reconfirm the current red state in the operating repo before any repair work starts.

Owner

- Agent A only

Inputs

- `exports/validation/replay_repair/2026-03-19/operating_vs_green_gap_report.md`
- current repo head and worktree status

Commands

- `cd ~/Docs/Autonomous_business`
- `python3 scripts/validate_params.py --strict --as-of 2026-03-19`
- `./.venv/bin/python scripts/run_owner_truth_daily.py --mode replay --as-of 2026-03-19 --strict`
- `./.venv/bin/python scripts/system_doctor.py --strict --project-root . --as-of 2026-03-19 --runtime-mode replay --truth-source webui_archive`

Definition of done

- current red state is captured
- current git/worktree state is recorded
- no changes are made in R0

Phase R1 — Proof Surface Recovery Plan

Goal

Determine exactly which missing proof artifacts can be restored as preserved evidence and which must be regenerated from canonical inputs.

Owners

- Agent B analyzes
- Agent A executes

Required output from Agent B

For each missing package/file, classify one of:

- `RESTORE_PRESERVED_PROOF`
- `REGENERATE_FROM_CANONICAL_INPUTS`
- `DO_NOT_TRANSPLANT_WITHOUT_NEW_PROVENANCE_DECISION`

Focus packages

- `exports/validation/webui_archive_single_truth/2026-03-19`
- `exports/validation/identity_stabilization/2026-03-09`
- `exports/validation/board_v8_runtime/2026-03-19`

Definition of done

- the exact restore-vs-regenerate map exists in agent output
- Agent A can execute without re-reading incident history

Stop-the-line criteria

- any proposal to copy derived proof artifacts without stating provenance
- any suggestion to widen semantics instead of restoring the real proof surface

Phase R2 — OPEX Provenance Resolution

Goal

Make the March replay OPEX artifact explicit, current enough for March 19 replay, and transparently sourced.

Owners

- Agent B analyzes
- Agent A executes

Required source review

- `config/opex/opex_schedule.yaml`
- validator references to the OPEX source workbook path
- `~/Documents/useful tables/Main crm spreadsheets/main tables/Purchase_orders/Finance/Loans_Master_V4.1_GPT.xlsx`
  - sheet `OPEX_SCHEDULE`
- any current repo-approved source workbook path already recorded in replay artifacts

Required output from Agent B

- canonical March replay OPEX source
- safest action:
  - `RESTORE_PROVEN_YAML`
  - `REGENERATE_YAML_FROM_APPROVED_SOURCE`
  - `BLOCKED_PENDING_SOURCE_DECISION`
- exact commands Agent A should run

Definition of done

- OPEX source is explicit
- freshness repair path is explicit
- no silent source substitution is allowed

Phase R3 — DB Divergence Triage

Goal

Isolate whether DB repair is still required after proof-surface and OPEX repair, and if so, make the repair minimal and reversible.

Owners

- Agent C analyzes
- Agent A executes only if needed

Required analysis scope

- `validate_params --strict --as-of 2026-03-19`
- `on_delivery_freeze`
- order chronology tied to the 57 `missing_in_db_orders`
- relevant order/status overlays
- archive-order API sales truth if chronology needs a tie-breaker

Required output from Agent C

- exact failing tables/rows/domains
- whether artifact + OPEX repair should be rerun first before DB writes
- if DB mutation is still necessary:
  - minimal write-gated repair hypothesis
  - backup requirements
  - rerun validators
  - rollback strategy

Definition of done

- DB repair is either ruled out for now or scoped narrowly enough for one controlled apply

Stop-the-line criteria

- broad DB rewrite suggestions
- any mutation proposal without backup-first and validator replay

Phase R4 — Integrated Repair Execution

Goal

Repair the operating repo in the smallest causal order and rerun the March replay gates until the true remaining blocker is exposed or green is achieved.

Owner

- Agent A only

Required order

1. restore/regenerate missing March proof artifacts
2. refresh OPEX replay artifact
3. rerun:
   - `python3 scripts/validate_params.py --strict --as-of 2026-03-19`
   - `./.venv/bin/python scripts/run_owner_truth_daily.py --mode replay --as-of 2026-03-19 --strict`
   - `./.venv/bin/python scripts/system_doctor.py --strict --project-root . --as-of 2026-03-19 --runtime-mode replay --truth-source webui_archive`
4. only if still blocked on DB truth, perform the write-gated DB repair
5. rerun all target gates

Definition of done

- March replay is green, or
- the remaining blocker is narrowed honestly to a new explicit stopline packet

Phase R5 — Transparent Closeout

Goal

Leave the repo in a transparent state where every repair decision is visible and every owner-domain artifact has explicit provenance.

Owner

- Agent A only

Required closeout contents

- commands actually run
- source manifest for restored/regenerated artifacts
- DB backup path if DB touched
- before/after gate summary
- exact remaining blocker if not green
- rollback steps for git and DB

Definition of done

- another agent can pick up the repo without hidden assumptions

One-agent fallback

If coordination overhead is too high, skip Agents B and C and let Agent A execute the whole plan sequentially. This is the safest path, but slower.

Delegation matrix

| Phase | Domain | Safe to delegate | Owner | Writes allowed |
| --- | --- | --- | --- | --- |
| R0 | baseline replay/status | no | Agent A | yes |
| R1 | proof artifact provenance | yes | Agent B analyze, Agent A execute | Agent A only |
| R2 | OPEX provenance/freshness | yes | Agent B analyze, Agent A execute | Agent A only |
| R3 | DB divergence triage | yes | Agent C analyze, Agent A execute if needed | Agent A only |
| R4 | integrated repair + reruns | no | Agent A | yes |
| R5 | closeout | no | Agent A | yes |

Complete prompt — Agent A

Work in `~/Docs/Autonomous_business` on the current branch. You are the only agent allowed to write files, rerun shared pipelines, update `.claude/*`, or mutate `db/app.db`. Read `AGENTS.md`, `docs/00_START_HERE.md`, and `docs/PLAN_OPERATING_REPO_MARCH19_GREEN_REPAIR_2026-04-15.md` first, then use `exports/validation/replay_repair/2026-03-19/operating_vs_green_gap_report.md` as the live stopline packet.

Objective: make the operating repo historically green and owner-decision ready for `as_of=2026-03-19`, matching the retained green worktree at `~/Docs/wt_webui_owner_truth_operationalization_v1`, without hiding provenance. Execute phases R0 through R5 in strict order. First confirm the baseline red state. Then restore or regenerate the missing March proof packages according to the read-only artifact analyst’s classifications. Then refresh the March replay OPEX artifact using the approved source/provenance path. Rerun `validate_params`, `run_owner_truth_daily`, and `system_doctor`. Only if replay remains blocked on DB truth after artifact and OPEX repair may you perform a write-gated DB repair with backup-first discipline. Keep blast radius small, do not loosen any validator, do not silently swap sources, and do not infer business truth from mutable logs. Record commands run, backup paths, before/after status, and rollback steps transparently.

Short prompt — Agent A

Work in `~/Docs/Autonomous_business` as the only write-capable agent. Read `AGENTS.md`, `docs/00_START_HERE.md`, and `docs/PLAN_OPERATING_REPO_MARCH19_GREEN_REPAIR_2026-04-15.md`, then execute phases R0 to R5 in order: proof artifacts, OPEX artifact, replay rerun, and DB repair only if still necessary.

Complete prompt — Agent B

Work read-only only. Use either a separate read-only worktree or direct inspection only; do not modify repo files, do not run write paths, and do not touch `.claude/*`. Read `AGENTS.md`, `docs/00_START_HERE.md`, `docs/PLAN_OPERATING_REPO_MARCH19_GREEN_REPAIR_2026-04-15.md`, and `exports/validation/replay_repair/2026-03-19/operating_vs_green_gap_report.md`.

Objective: produce the exact smallest safe recovery plan for the missing March proof packages and the March replay OPEX artifact. Compare `~/Docs/Autonomous_business` against `~/Docs/wt_webui_owner_truth_operationalization_v1`. For each missing package under `webui_archive_single_truth/2026-03-19`, `identity_stabilization/2026-03-09`, and `board_v8_runtime/2026-03-19`, classify it as `RESTORE_PRESERVED_PROOF`, `REGENERATE_FROM_CANONICAL_INPUTS`, or `DO_NOT_TRANSPLANT_WITHOUT_NEW_PROVENANCE_DECISION`. Then analyze OPEX provenance by comparing `config/opex/opex_schedule.yaml`, the validator’s expected source workbook path, and `~/Documents/useful tables/Main crm spreadsheets/main tables/Purchase_orders/Finance/Loans_Master_V4.1_GPT.xlsx` sheet `OPEX_SCHEDULE`. Return a concise report in chat only: exact restore-vs-regenerate map, canonical OPEX source for March replay, safest refresh path, and exact commands Agent A should run. If source provenance is unclear, say so explicitly.

Short prompt — Agent B

Read-only only: compare the operating repo against `~/Docs/wt_webui_owner_truth_operationalization_v1`, then classify the March proof artifacts as restore vs regenerate and resolve the safest canonical OPEX refresh path using `docs/PLAN_OPERATING_REPO_MARCH19_GREEN_REPAIR_2026-04-15.md`.

Complete prompt — Agent C

Work read-only only. Use either a separate read-only worktree or direct inspection only; do not modify repo files, do not write the DB, and do not touch `.claude/*`. Read `AGENTS.md`, `docs/00_START_HERE.md`, `docs/PLAN_OPERATING_REPO_MARCH19_GREEN_REPAIR_2026-04-15.md`, and the current stopline artifacts in the operating repo.

Objective: isolate the smallest exact DB divergence that keeps March 19 red after the code port. Focus on `python3 scripts/validate_params.py --strict --as-of 2026-03-19`, especially the `on_delivery_freeze` failure, and compare the operating repo against `~/Docs/wt_webui_owner_truth_operationalization_v1`, where the same gate passes. Inspect only the failing March replay surfaces: order chronology, on-delivery cost freeze, any rows tied to the 57 `missing_in_db_orders`, and related overlays. Use archive-order API sales truth as a chronology tie-breaker if needed. Return a concise report in chat only: exact failing tables/rows/domains, whether artifact and OPEX repair should be attempted first before DB mutation, and if DB mutation is still required, the minimal write-gated repair plan with backup requirements, rerun validators, and rollback steps. Do not suggest broad DB rewrites.

Short prompt — Agent C

Read-only only: compare the March 19 DB stoplines in the operating repo versus `~/Docs/wt_webui_owner_truth_operationalization_v1`, focusing on `validate_params --strict --as-of 2026-03-19` and `on_delivery_freeze`, and return the smallest exact DB repair hypothesis using `docs/PLAN_OPERATING_REPO_MARCH19_GREEN_REPAIR_2026-04-15.md`.

Launch order

If using all three agents:

1. launch Agent B
2. launch Agent C
3. keep Agent A idle until B and C return
4. Agent A executes R0 through R5 using B and C outputs

If using one agent:

1. launch Agent A only
2. execute R0 through R5 sequentially

Final note

This plan favors truth restoration over code churn. The code port is no longer the main problem. The repo needs the missing March proof surface, explicit OPEX provenance, and only then, if still necessary, a minimal write-gated DB repair.
