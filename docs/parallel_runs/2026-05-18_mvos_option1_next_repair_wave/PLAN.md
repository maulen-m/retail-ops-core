# MVOS Option 1 Next Repair Wave Plan

Created: `2026-05-18T19:07:35+05:00`

Status: `LAUNCH_APPROVED_FOR_COPIED_TEMP_ROOT_AGENTS`

Repo: `~/Docs/Autonomous_business`

## Purpose

Move from the owner-approved green repair wave review toward a copied-temp 10/10 proof by repairing the remaining yellow domains without production writes or hidden blockers.

This is the approved Option 1 route after:

- `~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_owner_approved_green_repair/ORCHESTRATOR_REVIEW_AFTER_901_904.md`
- `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-18_mvos_owner_approved_green_repair/OWNER_QA_COMPLETION_AUDIT.md`

## Current Boundary

Accepted rebaseline:

- DB SHA-256: `8d45d928888b0a03b42d8a2e73638a5f0ac30caa82b45943623e8df6433196d3`
- workbook SHA-256: `0dd9da0233fd30607b6f858db2ea7532bc9ec954021f5e9c195814a41d128313`
- SQLite integrity: `ok`
- all-business automation verify at `2026-05-18T19:07:24+05:00`: `ok=true`, `loaded_count=0`, `quiet_cron=true`, `quiet_protected_surfaces=true`

If an execution agent observes a different protected DB/workbook SHA at start, it must stop `RED` and write a closeout. Do not silently rebaseline.

## Owner Approval

The human owner approved starting Option 1 in the orchestrator chat on `2026-05-18` after receiving the recommendation to launch the next copied-temp repair wave.

This approval authorizes:

- read-only analysis;
- copied-temp DB proof writes only;
- local evidence generation;
- local closeout writing;
- use of existing local evidence only for the `177` missing order-entry rows, when evidence is identity-bearing and auditable.

This approval does not authorize:

- production DB writes;
- workbook writes;
- scheduler, LaunchAgent, or cron changes;
- source-pointer writes;
- Web_automation mutation;
- Kaspi/API/WebUI writes;
- ad-platform writes;
- bank/cash movement;
- supplier payment;
- PO commitment;
- stock changes;
- price changes;
- owner publication/send;
- external writes;
- production apply.

## Scope Profile

`MVOS_SCOPE_ACTIVE_BUSINESS_THREE_STORE`

Included:

- `STOREB`
- `ACMEWEAR`
- `UNIVERSAL`

Excluded until future owner reactivation:

- `11KZ`
- `MELVIS`

Required disclosure:

```text
SCOPED_STATUS_LEDGER_STOREB_ACMEWEAR_UNIVERSAL_ONLY
11KZ_AND_MELVIS_EXCLUDED_FROM_CURRENT_OPERATING_SCOPE
NO_FULL_FIVE_STORE_STATUS_LEDGER_GREEN
```

## Root Repair Agents

Agents `905`, `906`, and `907` may run in parallel. They may not edit shared repo code or production surfaces. They may write only assigned evidence folders and closeouts.

| Agent | Domain | Closeout |
| --- | --- | --- |
| `905` | Order-entry source hierarchy and 177 missing recent rows | `~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_option1_next_repair_wave/agent905_order_entry_source_hierarchy_repair_closeout.md` |
| `906` | Stock snapshot, stock ledger, PO money gate, Line61 shortage route | `~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_option1_next_repair_wave/agent906_stock_po_shortage_repair_closeout.md` |
| `907` | Cashflow stale tables, accepted source freshness bridge, policy-gate integration | `~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_option1_next_repair_wave/agent907_cashflow_source_freshness_integration_closeout.md` |

## Gated Synthesis Agent

Agent `908` must not run until the orchestrator reviews Agents `905`, `906`, and `907`.

| Agent | Domain | Closeout |
| --- | --- | --- |
| `908` | Combined copied-temp 10/10 proof rerun and CodeCaptain packet decision | `~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_option1_next_repair_wave/agent908_combined_synthesis_proof_closeout.md` |

Agent `908` may be launched only after root closeouts exist. If any root agent is `RED`, do not launch `908`. If any root agent is `YELLOW`, launch `908` only as a synthesis/CodeCaptain-packet writer that preserves retained blockers; do not let it claim copied-temp green.

## Expected Root Outcomes

Agent905 should produce one of:

- `GREEN`: the `177` missing recent rows are resolved on copied DB using identity-bearing local evidence, with validator proof and no header-only leakage.
- `YELLOW`: some or all rows lack identity-bearing evidence and remain quarantined/visible.
- `RED`: protected boundary drift, unsafe source use, production write attempt, or hidden blocker.

Agent906 should produce one of:

- `GREEN`: copied-temp stock snapshot/ledger proof and PO money gate are green for the declared scope, with the Line61 23-unit shortage treated as real.
- `YELLOW`: fresh stock or PO source route remains missing, but blockers are visible.
- `RED`: protected boundary drift, workbook mutation, stock/PO mutation, or hidden shortage/blocker.

Agent907 should produce one of:

- `GREEN`: copied-temp cashflow/source freshness/policy gates pass after using only accepted rows and domain materializers.
- `YELLOW`: stale cashflow tables or non-lane sources remain visible.
- `RED`: protected boundary drift, production mutation, unaccepted bridge rows, or false green.

## Do Not Do Yet

- Do not run production preflight.
- Do not production-apply any repair.
- Do not resume schedulers.
- Do not publish owner outputs.
- Do not hide the 9 high-stock retained blockers.
- Do not claim full five-store status-ledger green.
- Do not insert header-only rows into `fact_order_entries_kaspi`.
