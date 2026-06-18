# CodeCaptain Appendix Prompt: Phase 7 Offer-Linkage Optional Narrowing

Please review this as an appendix to the current Phase 4/5 MVOS yellow boundary. This appendix is copied-temp only and does not ask for production preflight or apply authority.

## Question

Agent16 materialized `fact_offer_stock_mapper_current` on a copied DB only. Does this correctly narrow `B008_po_money_gate` optional `offer_linkage` from `mapper table missing` to exact retained defects, while keeping PO money `STOP` because required `single_truth_alignment` physical-stock drift remains?

## Facts

- Mapper rows built on copied DB only: `2640`
- `validate_offer_linkage.py`: `ok=False`, `resolved=2462`, `unresolved=91`, `ambiguous=87`, `missing_bidirectional=4`
- `validate_po_money_gate.py --json`: `ok=false`, required failed `single_truth_alignment`, optional failed `offer_linkage`
- Required physical-stock drift remains unchanged:
  - snapshot date `2026-05-04`
  - diff `16,835,338.88 KZT`
  - allowed `803,909.74 KZT`

## Requested Review

1. Confirm that `B008_po_money_gate` should remain `STOP`.
2. Confirm that optional `offer_linkage` is now a precise future repair lane rather than a missing-table blocker.
3. Confirm whether offer-linkage repair should wait behind the required physical-stock/single-truth alignment decision, or whether strict offer-linkage must be repaired before any later production-preflight conversation.

No production DB write, workbook write, source-pointer write, scheduler change, external write, Web_automation write, Kaspi/API/WebUI mutation, ad-platform write, stock/price/cash/PO action, owner publication, production preflight, or production apply is requested.
