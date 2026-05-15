# Agent 41 - AB Web Automation DirectAPI Source Bridge

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_41_ab_wa_directapi_source_bridge_closeout.md`

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/ORCHESTRATOR_REVIEW_AFTER_AGENT_36.md`
5. `~/Docs/Web_automation/runs/ab_ads_source_refresh_data_gathering/20260505_source_packet_standardization/WA_AGENT_38_KASPI_MARKETING_SOURCE_PACKET_STANDARDIZATION_CLOSEOUT.md`
6. this starter prompt

## Dependency

Do not start until Agent 38 is complete and its packet is `GREEN`.

## Mission

Implement the narrow AB C3 observer bridge for the strict Web_automation Kaspi Marketing source-freshness packet produced by Agent 38, then prove it on a copied Agent 36 temp DB.

## Write Boundary

Allowed:

- tests first;
- narrow source-freshness code and tests only if Agent 38 produced a strict packet;
- temp DB and evidence under `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_41_evidence/`;
- assigned closeout.

Forbidden:

- production DB writes;
- workbook edits;
- Web_automation writes;
- live API/browser calls;
- treating stale/missing packet fields as fresh.

## Required Packet

`~/Docs/Web_automation/runs/ab_ads_source_refresh_data_gathering/20260505_source_packet_standardization/kaspi_marketing_source_freshness_packet.json`

## Required Work

1. Write failing tests proving:
   - strict `GREEN` packet clears `src_web_automation_kaspi_marketing_directapi`;
   - missing packet fails closed;
   - non-GREEN packet fails closed;
   - missing no-write fields fail closed;
   - missing store/date coverage through `2026-05-04` fails closed;
   - SQLite hash/path mismatch fails closed.
2. Implement the narrow bridge.
3. Copy Agent 36 DB to Agent 41 evidence and materialize C3 source freshness and gates.
4. Confirm the only remaining source freshness blocker is not the directapi source if the packet is strict `GREEN`.

## Required Gates

Run and record:

```bash
python3 -m py_compile core/ops/policy_materialization_c3.py tests/test_policy_materialization_c3.py
pytest -q tests/test_policy_materialization_c3.py -k 'web_automation_kaspi_marketing or directapi'
pytest -q tests/test_policy_materialization_c3.py tests/test_policy_registry_c3_contract.py
python3 scripts/validate_policy_source_freshness.py --db ~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_41_evidence/agent41_wa_directapi_bridge_temp_20260504.db --as-of 2026-05-04 --strict --json
python3 scripts/validate_policy_gate_results.py --db ~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_41_evidence/agent41_wa_directapi_bridge_temp_20260504.db --strict --json
git status --short -- db/app.db excel_ui/SALES_KSP_CRM_V3.xlsx
```

## Expected Gate

`GREEN` only if the strict packet clears the source without weakening fail-closed behavior and no other regressions appear.

`YELLOW` if the bridge is correct but strict publication still blocks on cashflow/order-entry/exception residuals.

`RED` if the bridge over-trusts evidence or hides stale ads source truth.
