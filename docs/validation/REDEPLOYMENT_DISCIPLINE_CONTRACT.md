# Redeployment Discipline Contract

Gate: G-CASH-04

Purpose: liquidation proceeds must stay as cash until the required truth stack is green. This prevents recovery leakage: turning markdown proceeds into new stock purchases while stock truth, cash truth, or PPCH are still unresolved.

## Authority

- Owner decision: OD-009 keeps auto-PO governed off.
- Extension rule: EXT-L06 says liquidation proceeds are held as cash until stock/cash/PPCH-v1 gates are green.
- Liquidation dependency: G-LIQ-02 must be green before any liquidation-proceeds ledger row is considered mature.

## Required Green Stack

Redeployment from liquidation proceeds is forbidden unless all of these are green at the same review time:

- G-LIQ-02
- G-STOCK-03
- G-STOCK-05
- G-CASH-02
- G-CASH-03
- G-MET-01

## Ledger Contract

The ledger is a local control artifact, not a money movement instruction. It records proceeds and redeployment decisions only after liquidation starts.

Required columns:

- ledger_id
- tranche_id
- owner_decision_id
- proceeds_event_ref
- proceeds_amount_kzt
- proceeds_received_date
- redeployment_decision
- redeployment_amount_kzt
- redeployment_ref
- gate_snapshot
- allowed
- notes

`redeployment_amount_kzt > 0` while any required gate is not green is a RED violation. `HELD_AS_CASH` rows with zero redeployment amount are allowed while the stack is not green.

## Report Semantics

- RED: any ungated redeployment is found in the ledger or DB guard probes.
- ARMED: the guard exists and proves zero ungated redeployments, but liquidation has not started, prerequisite gates are not green, or no mature proceeds-ledger row exists yet.
- GREEN: G-LIQ-02 and the full required stack are green, at least one proceeds-ledger review row exists, and no ungated redeployment is present.

The report is read-only against production DB and must not write DB, workbook, Google Sheet, Telegram, Kaspi, Repricer, stock, price, LaunchAgent, customer, or operator-message surfaces.
