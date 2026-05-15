# Agent761 - Stock and Order Risk Read-Only MVOS Report

You are Agent761 in the MVOS fast-track wave.

Gate target: `GREEN` if you produce a review-only stock/order risk report with clear evidence and no mutations.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/MVOS_FASTTRACK_INTEGRATION_RECORD_20260511_141731.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/10_DAY_MVOS_FASTTRACK_CHARTER_20260511_141731.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/MVOS_FASTTRACK_ORCHESTRATOR_HANDOFF_20260511_141731.md`
6. This starter prompt.

## Scope

Read-only only. Inspect stock/order risk surfaces needed for a survival brief: fulfillment risk, stale source labels, exception queues, product warning cohorts, and order/stock boundaries.

Do not edit repo files. Do not write DB/workbook/export truth. Do not run apply paths. Do not request owner approval.

## Required Output

Write your closeout here:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/mvos_fasttrack_20260511_141731_agent761_stock_order_risk_readonly_closeout.md`

Your closeout must include:

- standalone `Gate: GREEN/YELLOW/RED` line;
- commands run;
- stock/order risks that should appear in Daily Survival Brief v1;
- warnings that must remain visible;
- allowed review-only statements;
- blocked price, stock, PO, and owner-publication decisions;
- evidence paths used.

## Stoplines

Stop `RED` if a source would force productizing warning rows. Stop `YELLOW` if the data can inform review but cannot support a clean daily brief statement.
