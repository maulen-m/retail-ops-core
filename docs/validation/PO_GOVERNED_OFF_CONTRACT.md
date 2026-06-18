# PO Governed-Off Contract

## Purpose

`G-PO-01` is green when auto-PO is deliberately governed OFF, not when the
system silently fails to create purchase orders.

## Authority

- Owner decision: `OD-009`.
- Owning PO logic: `docs/protocol/active/PO_making_logic_v3.md`.
- Machine-readable gate config:
  `config/validation/po_governed_off_gates.json`.

## Required Proof

The report must prove:

- `fact_po_draft`, `fact_po_draft_lines`, and `fact_po_execution` have zero
  production rows.
- No installed user LaunchAgent points to `run_auto_po.py` or an auto-PO label.
- OD-009 restart criteria are recorded.
- The six stop-buy gates are encoded for manual PO advice:
  `frozen_cover_gt_180d`, `size_overstock`, `return_qc_telemetry`,
  `ppch_v1_gate`, `cash_truth_gate`, and `ads_crr_gate`.
- `validate_po_money_gate.py` required checks pass.
- `validate_po_contract.py` golden fixtures pass.
- The current advisory proposal artifact passes
  `validate_po_capital_protection.py`.

## Non-Authorization

This contract does not authorize purchasing, PO draft creation, supplier
contact, Telegram notification, workbook writes, DB writes, or scheduler
installation. Proposal rows generated for this proof are advisory audit inputs
only. `G-PO-02` remains responsible for rebuilding size priors and proving
forecast quality before any restart can be considered.

## Command

```bash
PYTHONPATH=. .venv/bin/python scripts/report_po_governed_off.py --as-of 2026-06-17 --run-subvalidators --strict
```

## Outputs

The command writes:

- `exports/validation/po_governed_off/<as_of>/po_governed_off_report.json`
- `exports/validation/po_governed_off/<as_of>/po_governed_off_report.md`

`status=GREEN` means governed OFF is proved. It never means auto-PO is enabled.
