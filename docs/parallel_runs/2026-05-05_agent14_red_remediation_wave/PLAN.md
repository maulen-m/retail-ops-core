# Agent 14 RED Remediation Wave Plan

Generated: `2026-05-05`

## Objective

Turn Agent 14's broad RED stopline into exact, safe implementation lanes.

Do not weaken publication gates. Do not publish owner green. Do not apply production writes in this wave.

## Current Accepted State

Accepted after Agent 13:

- lifecycle production repair applied;
- PO/inbound production repair applied;
- production DB integrity passed;
- operational integration gate now has ads-only findings.

Agent 14 then rematerialized C3 policy state and produced a blocked owner brief. It remained RED because strict C3/source policy failures were broader than ads-only.

## Root Blocker Families

1. Ads source truth:
   - `ads_source_refresh_runs=0`
   - `ads_campaign_product_daily=0`
   - WA1 ACMEWEAR and WA2 STOREB closeouts are both YELLOW due Kaspi Marketing `429` limits.

2. Operational derived-table freshness:
   - `stock_ledger` max event date: `2026-04-15`
   - `sales_fact_v2` max order date: `2026-04-15`
   - `fact_cashflow_daily` max date: `2026-04-15`
   - `fact_order_entries_kaspi` already reaches `2026-05-04`, which makes the old `2026-05-03` brief future-dated.

3. C3 policy/source freshness semantics:
   - external repo directory mtime checks are stale for E-commerce/Sourcing/Facebook roots;
   - inbound workbook is future-dated relative to the old `2026-05-03` as-of;
   - policy may need narrower artifact pointers or recursive/latest-artifact semantics.

4. Exception queue semantics:
   - open high-severity stock exceptions are intentional owner overrides/quarantine holds, but current policy treats them as publication blockers.
   - need determine whether they should remain high/blocking, be converted into accepted active controls, or be separated from owner-publication blockers.

## Agent Split

Agent 15: derived-table freshness replay plan.

Agent 16: C3 policy/source freshness and exception semantics.

Agent 17: ads evidence/retry/import plan.

## Success Criteria

Each agent must return:

- `Gate: GREEN/YELLOW/RED`
- exact blocker classification;
- exact commands/scripts for the next implementation lane;
- whether production writes are safe later;
- stoplines and owner-attention requirements.
