# Agent 748 - Current `dec77` Independent Confirmation

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_748_current_dec77_independent_confirmation_closeout.md`

Assigned evidence folder:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_748_current_dec77_independent_confirmation_evidence/`

Parallel group:

`agent747_748_current_dec77_reanchor_root`

## Mission

Independently confirm the current production DB boundary after Agent746 forensics. This is a read-only confirmation lane. It must not mutate production DB, workbook, schedulers, external systems, or Option C state.

## Required Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/TMUX_PING_ROUTING_INCIDENT_20260509.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_746_orchestrator_db_drift_forensics_closeout.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_746_orchestrator_db_drift_forensics_evidence/`

## Expected Current Boundary

- DB SHA: `dec77f37cc63147e54e9085a6a0f9564d9ead9e57aea0d8483dc0473886bee64`
- Workbook SHA: `3ad4b81c39b125c48b34c02afb8a30eafd348658e07afd27c11f628b8987025c`
- DB integrity: `ok`
- strict product-identity quarantine rows: `23`
- header-only quarantine table rows: `252`
- combined quarantine cohort: `275`
- operational validator visible product-identity warnings: `23`
- operational validator visible header-only warnings: current expected `249`
- leakage status for warning cohorts: `NO_PRODUCT_LEAKAGE`
- cash preservation: strict `123528.34`, header-only `993344.51`, combined `1116872.85`

## Write Boundary

Allowed writes:

- assigned closeout;
- assigned evidence folder only.

Forbidden:

- Do not mutate `~/Docs/Autonomous_business/db/app.db`.
- Do not mutate `~/Docs/Autonomous_business/excel_ui/SALES_KSP_CRM_V3.xlsx`.
- Do not mutate schedulers or LaunchAgents.
- Do not write to external systems, Kaspi/API, ads platforms, Google, banks, browser automation, Web_automation, or external repos.
- Do not install or enable Option C automation.
- Do not ask owner for approval.
- Do not reuse old Agent54 phrase or activate Agent64.

## Required Checks

Run and save outputs under the assigned evidence folder:

```bash
date '+%Y-%m-%dT%H:%M:%S%z'
shasum -a 256 db/app.db excel_ui/SALES_KSP_CRM_V3.xlsx
stat -f '%N\t%z\t%m\t%Sm' db/app.db excel_ui/SALES_KSP_CRM_V3.xlsx
sqlite3 -readonly db/app.db 'PRAGMA integrity_check; PRAGMA schema_version; PRAGMA page_count; PRAGMA freelist_count;'
lsof db/app.db excel_ui/SALES_KSP_CRM_V3.xlsx || true
ls db/app.db-wal db/app.db-shm db/app.db-journal 2>/dev/null || true
python3 scripts/validate_policy_source_freshness.py --strict --json
python3 scripts/validate_operational_stock_integration_gates.py --json
python3 scripts/validate_order_cashflow_coverage.py --as-of 2026-05-04 --strict --json
python3 scripts/validate_cashflow_actual_model_separation.py --anchor-date 2026-05-04 --strict --json
python3 scripts/validate_cashflow_invariants.py
python3 scripts/validate_write_side_gating.py --manifest config/write_side_gating_manifest.yaml
scripts/check_no_db_tracked.sh
scripts/lint_docs.sh
```

Also independently query and save:

- key table row counts for:
  - `source_freshness_result`
  - `ads_source_refresh_runs`
  - `ads_campaign_product_daily`
  - `sales_fact_v2`
  - `stock_ledger`
  - `fact_inventory_snapshot_size`
  - `order_status_event`
  - `fact_cashflow_events`
  - `fact_cashflow_daily`
  - `fact_order_entries_kaspi`
  - `fact_order_entry_product_identity_quarantine`
  - `fact_order_entry_header_only_source_gap_quarantine`
  - `view_sales_line_truth`
- warning visibility for strict `23`, header-only `252`, validator-visible product warnings, and validator-visible header warnings.
- leakage/cash preservation status for strict `23`, header-only `252`, and combined `275`.

## Gate Semantics

`GREEN`:

- current DB/workbook hashes match expected values at initial and final samples;
- DB integrity is `ok`;
- no unsafe holders/sidecars;
- final validators pass;
- key counts match Agent746 expected values or any drift is proven harmless/read-only;
- warning cohorts remain visible and non-productized;
- leakage and cash preservation match expected targets;
- no forbidden mutation occurred.

`YELLOW`:

- validators pass but there is dirty-state ambiguity, harmless holder ambiguity, or non-critical mismatch requiring orchestrator review.

`RED`:

- DB/workbook SHA mismatch;
- DB integrity failure;
- validator failure;
- hidden warning cohorts;
- product leakage;
- cash-preservation mismatch;
- any forbidden mutation.

## Closeout

Write the closeout with READCHECK, commands run, evidence paths, expected-vs-actual matrix, validator matrix, warning/leakage/cash summary, mutation statement, recommended next step, and standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.
