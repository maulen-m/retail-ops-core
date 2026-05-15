# Agent831 - Sales Fact Identity Blockers

Gate target: `GREEN` if all six strict `sales_fact_v2` blockers have source-backed decisions or exact quarantine routes. Use `YELLOW` if any source/owner decision is still required.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-15_mvos_source_decision_wave/PLAN.md`
4. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_SOURCE_DECISION_WAVE_20260515_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
5. `~/Docs/Autonomous_business_agent_handoffs/2026-05-15_mvos_execution_wave/agent821_sales_fact_strict_blockers_closeout.md`
6. `~/Docs/Autonomous_business/exports/validation/mvos_execution_wave/20260515_111124/agent827_mvos_command_board/MVOS_OWNER_ACTION_LIST.md`
7. this starter prompt

## Assignment

Build the strict sales-fact identity decision packet.

Evidence root:

`~/Docs/Autonomous_business/exports/validation/mvos_source_decision_wave/20260515_134601/agent831_sales_fact_identity_blockers/`

Required report:

`~/Docs/Autonomous_business/exports/validation/mvos_source_decision_wave/20260515_134601/agent831_sales_fact_identity_blockers/SALES_FACT_IDENTITY_DECISION_PACKET.md`

Closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-15_mvos_source_decision_wave/agent831_sales_fact_identity_blockers_closeout.md`

## Required Work

Investigate exactly these blockers:

- `913421682` store `UNIVERSAL` offer `132822924_328581041`: missing active SKU mapping.
- `914238753` store `STOREB`: missing required `sku_identity`.
- `914286181` store `STOREB`: missing required `sku_identity`.
- `914319851` store `STOREB`: missing required `sku_identity`.
- `914340762` store `STOREB`: missing required `sku_identity` plus XL vs 3XL conflict.
- `914363937` store `STOREB`: missing required `sku_identity`.

Use only source-backed evidence. Do not invent SKU, size, product ID, product economics, or identity. If an exact source-backed fix is not available, propose the exact quarantine or owner/source decision needed.

## Boundaries

Read-only and copied-temp diagnostics only. No production DB write, workbook write, scheduler mutation, external write, owner publication, cash, PO, ads, price, stock, or lifecycle/status production repair.

Gate: GREEN
