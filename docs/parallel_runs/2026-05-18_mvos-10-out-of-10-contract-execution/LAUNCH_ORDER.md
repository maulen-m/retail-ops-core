# Launch Order

Use the starter folder:

`~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_10_OUT_OF_10_CONTRACT_EXECUTION_20260518_STARTERS`

Launch first:

```text
Read the repo bootstrap context and execute ~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_10_OUT_OF_10_CONTRACT_EXECUTION_20260518_STARTERS/01_AGENT_1__SCOPE_REGISTRY_BOUNDARY__SEQUENTIAL.md
```

Launch in parallel only after Agent 1 closes out and the orchestrator reviews its gate:

```text
Read the repo bootstrap context and execute ~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_10_OUT_OF_10_CONTRACT_EXECUTION_20260518_STARTERS/02_AGENT_2__C3_SOURCE_FRESHNESS__PARALLEL_AFTER_01.md
Read the repo bootstrap context and execute ~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_10_OUT_OF_10_CONTRACT_EXECUTION_20260518_STARTERS/03_AGENT_3__ORDERS_SALES_LIFECYCLE__PARALLEL_AFTER_01.md
Read the repo bootstrap context and execute ~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_10_OUT_OF_10_CONTRACT_EXECUTION_20260518_STARTERS/04_AGENT_4__ADS_TRUTH__PARALLEL_AFTER_01.md
Read the repo bootstrap context and execute ~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_10_OUT_OF_10_CONTRACT_EXECUTION_20260518_STARTERS/05_AGENT_5__CASHFLOW_BANK__PARALLEL_AFTER_01.md
Read the repo bootstrap context and execute ~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_10_OUT_OF_10_CONTRACT_EXECUTION_20260518_STARTERS/06_AGENT_6__PO_STOCK_EXCEPTION__PARALLEL_AFTER_01.md
```

Launch only after Agents 2-6 close out and the orchestrator reviews their gates:

```text
Read the repo bootstrap context and execute ~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_10_OUT_OF_10_CONTRACT_EXECUTION_20260518_STARTERS/07_AGENT_7__SYNTHESIS_COPY_TEMP_PREFLIGHT__AFTER_02_03_04_05_06.md
```
