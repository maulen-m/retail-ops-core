# Agent 3 Starter - Serialized Integrator

You are Agent 3. You are the only write-capable execution agent in Round 3.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-06-01_line31_green_except_creative_round3_strict_unrelated_repair/PLAN.md`
4. `~/Docs/Autonomous_business/docs/agent_handoffs/LINE31_GREEN_EXCEPT_CREATIVE_ROUND3_STRICT_UNRELATED_20260601_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/LINE31_GREEN_EXCEPT_CREATIVE_ROUND3_STRICT_UNRELATED_20260601_STARTERS/03_AGENT_3__SERIALIZED_INTEGRATOR__AFTER_1_2.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-06-01_line31_green_except_creative_round3_strict_unrelated_repair/agent1_strict_authority_scout_closeout.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-06-01_line31_green_except_creative_round3_strict_unrelated_repair/agent2_unrelated_failure_triage_closeout.md`
8. `~/.codex/skills/write-gated-db-repair/SKILL.md`

## Objective

Repair the owner-requested option 2 unrelated failures first where safe, then repair or durably classify the remaining LINE31 strict blockers, and rerun launch-readiness gates.

## Write Authority

You may modify repo code/docs/config/tests and may perform production `db/app.db` repair only for named strict blockers when all write-gated requirements are satisfied:

- pre-write backup;
- explicit evidence of authority;
- before/after row evidence;
- SQLite integrity check;
- validator replay;
- rollback instructions.

You may not perform Meta publish, website deploy, Cloudflare mutation, Kaspi/API/WebUI/CRM mutation, source-pointer/scheduler mutation, external writes, price changes, stock offer changes, cash movement, supplier payment, PO commitment, owner publication, or invented COGS/cost values.

## Required Work

1. Read Agent 1 and Agent 2 closeouts.
2. Repair safe unrelated broad-suite failures first, using Agent 2's queue. Do not get stuck on broad failures that are stale/environmental/out-of-scope; classify them with evidence.
3. Repair or durably classify strict blockers using Agent 1's authority map:
   - on-delivery missing cost balances for `938256969`, `940453925`, `941824782`;
   - unresolved production COGS for `909054064` / `SUIT-31-TS_3XL`;
   - profit publication lock from unresolved COGS;
   - stock snapshot freshness invariant.
4. Preserve owner facts:
   - cash and SHR payment truth from current workbook;
   - 18th `7000 CNY` SHR payment is paid;
   - protected reserve is `800000 KZT`;
   - LINE31 stock uses April leftovers plus PO1-A arrival;
   - creative remains later-only.
5. Rerun:
   - `python3 scripts/validate_params.py --strict`
   - `python3 scripts/validate_on_delivery_freeze.py --until 2026-05-31`
   - `python3 scripts/validate_cogs_integrity.py --as-of 2026-05-31`
   - `python3 scripts/validate_profit_publication_integrity.py --as-of 2026-05-31`
   - `python3 scripts/validate_po_dashboard_invariants.py`
   - targeted tests for touched files;
   - `scripts/check_no_db_tracked.sh`
   - `bash scripts/lint_docs.sh`
   - DB `PRAGMA integrity_check`.

## Required Evidence Folder

`~/Docs/Autonomous_business/exports/validation/line31_green_except_creative_round3_strict_unrelated_repair_20260601/agent3_serialized_integrator/`

Required files:

- `before_after_gate_matrix.md`
- `unrelated_failure_repair_matrix.csv`
- `strict_blocker_repair_matrix.csv`
- `production_mutation_ledger.md`
- `validator_replay_summary.md`
- `COMMANDS_RUN.tsv`

## Assigned Closeout

`~/Docs/Autonomous_business_agent_handoffs/2026-06-01_line31_green_except_creative_round3_strict_unrelated_repair/agent3_serialized_integrator_closeout.md`

Closeout must include standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.

Use `GREEN` only if strict validators pass or all retained failures have durable launch-accepted authority. Use `YELLOW` for honest retained blockers.
