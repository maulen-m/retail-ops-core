# Agent 1: Scope, Source Registry, And Boundary Gate

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/contracts/MVOS_10_OUT_OF_10_DECISION_GRADE_ACCEPTANCE_CONTRACT.md`
5. `~/Docs/Autonomous_business/docs/contracts/MVOS_10_OUT_OF_10_ORCHESTRATOR_GOAL_PROMPT.md`
6. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-18_mvos-10-out-of-10-contract-execution/PLAN.md`
7. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_10_OUT_OF_10_CONTRACT_EXECUTION_20260518_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
8. this assigned starter prompt

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos-10-out-of-10-contract-execution/agent1_scope_registry_boundary_closeout.md`

Assigned evidence folder:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos-10-out-of-10-contract-execution/agent1_scope_registry_boundary_evidence`

## Task

Execute Phases 0-2 from the MVOS 10/10 contract:

- READCHECK and scope profile declaration.
- Source contract registry validation and gap map.
- Boundary and write-safety gate, including no-help-writes coverage.

You are the only write-capable repo agent in this first sequence. Keep edits minimal and focused on contract-supporting docs, local validators, tests, and non-production evidence. Do not mutate protected production surfaces.

## Required Outputs

Create or refresh evidence for:

- `READCHECK.md`
- `MVOS_SCOPE_PROFILE_DECLARATION.json`
- `SOURCE_CONTRACT_REGISTRY_GAP_MAP.md`
- `WRITE_SAFETY_AND_BOUNDARY_GATE.json`
- validator/test implementation notes if required validators are missing

Run if available, or implement tests-first before claiming green:

```bash
python3 -m json.tool docs/contracts/mvos_source_contracts/ACTIVE_MVOS_SOURCE_CONTRACT_REGISTRY.json
python3 scripts/validate_mvos_source_contract_registry.py --strict
scripts/check_no_db_tracked.sh
sqlite3 -readonly db/app.db 'PRAGMA integrity_check;'
python3 scripts/validate_write_side_gating.py --manifest config/write_side_gating_manifest.yaml --strict
python3 scripts/validate_no_help_command_writes.py --strict
pytest -q tests/test_generate_po_dashboard_data_help_no_write.py
```

## Boundary

Allowed: repo docs/code/tests, read-only DB inspection, local evidence, copied-temp-only diagnostics under your evidence folder.

Forbidden: production DB writes, protected workbook writes, scheduler mutation, LaunchAgent/cron mutation, Web_automation writes, browser-login automation, external writes, owner publication, cash, PO, stock, price, or ad-platform action.

## Gate Guidance

Use `Gate: GREEN` only if scope is explicit, registry is valid or has tests-first implementation with no active conflicts, and write-safety/no-help-writes checks pass.

Use `Gate: YELLOW` if a validator must still be implemented, a source contract requires owner/CodeCaptain decision, or a blocker remains but the boundary is safe.

Use `Gate: RED` if any protected surface drift, hidden write, registry contradiction, or help-command write is found.
