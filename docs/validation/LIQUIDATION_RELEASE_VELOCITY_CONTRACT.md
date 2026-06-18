# Liquidation Release Velocity Contract

Gate: G-LIQ-03

Purpose: keep liquidation markdowns governed after tranche execution. The system must publish weekly release velocity and must only escalate tiers using measured sell-through against owner stop rules.

## Inputs

- G-LIQ-01 liquidation register summary and segment map.
- G-LIQ-02 tranche ledger rows after tranche execution.
- G-WA-01 lead-store map rows for every active tranche row.

## Required Tranche Row Fields

- tranche_id
- sku_key
- tier
- release_date
- released_units
- sold_units
- floor_version
- stock_confidence
- rollback_price
- owner_decision_id

## Rule Semantics

- T1/T2/T3 dwell windows come from OD-005.
- Sell-through below 3 percent after the dwell window means stop/hold, not escalation.
- T4/T5 are parked for wave 1 unless a later owner decision explicitly authorizes them.
- Any active tranche row without a matching active lead-store map row is RED.

## Status Semantics

- GREEN: G-LIQ-02 is green, active tranche rows exist, required row fields are present, lead-store rows match, and no dwell/sell-through/parked-tier rule is violated.
- ARMED: the report exists but tranche execution has not started or no active tranche rows exist yet.
- RED: tranche rows violate required fields, lead-store mapping, parked-tier, dwell, or sell-through rules.

This report is local/read-only and does not upload prices, write DB rows, edit workbooks, send messages, or change LaunchAgents.
