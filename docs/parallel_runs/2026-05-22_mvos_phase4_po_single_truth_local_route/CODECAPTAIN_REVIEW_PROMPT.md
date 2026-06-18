# CodeCaptain Review Prompt: Phase 4 PO Single-Truth Local Route

Please review this scoped non-production Autonomous_business evidence pack.

The owner-approved boundary is copied-temp/read-only only. No production DB writes, workbook writes, source-pointer writes, scheduler/LaunchAgent/cron changes, Web_automation writes, Kaspi/API/WebUI mutations, external writes, ad-platform writes, ad spend, stock changes, price changes, cash movement, PO commitment, owner publication, production preflight, or production apply are authorized.

## What Changed

The orchestrator continued the MVOS blocker-closure wave after Phase 3 stayed YELLOW. The focused goal was to determine whether `B006`/`B007`/`B008` were still genuinely blocked or partly blocked by stale repo-export evidence.

Two small code/test changes were made:

- `scripts/generate_po_dashboard_data.py` now accepts evidence-local copied DB and output paths, plus a copied-temp `--plan0-anchor-message-date` override.
- `scripts/validate_po_money_gate.py` now accepts `--single-truth-system-dashboard` so the composite PO money gate can send the same evidence-local dashboard to `validate_single_truth_system.py`.

## Evidence Result

- `B006_single_truth_system` now passes in copied-temp scope when the validator uses the dashboard generated from the same copied DB.
- `B007_single_truth_alignment` no longer fails on missing dashboard `pos` data or `PO-4.0` quantity mismatch.
- With current PLAN-0 diagnostic anchor and `--skip-drift`, `validate_single_truth_alignment.py` passes.
- Full `validate_single_truth_alignment.py` still fails physical-stock inventory cost drift:
  `snapshot_date=2026-05-04`, `diff_kzt=16,835,338.88`, `allowed_kzt=803,909.74`.
- `B008_po_money_gate` remains false because `single_truth_alignment` is still a required failure.

The owner has explicitly confirmed no fresher physical stock data exists than the last source already used. Please keep that owner fact as controlling.

## Review Questions

1. Is the `B006_single_truth_system` copied-temp closure valid under the declared non-production boundary?
2. Is the `--single-truth-system-dashboard` composite-gate adapter correct and safe, or should the PO-money gate use a different parameter name/contract?
3. Is the `--plan0-anchor-message-date` copied-temp diagnostic override acceptable as a proof-only route, and should it become a reviewed production contract later?
4. Given no fresher physical stock source exists, what is the safest next route for `B007` and `B008`?
5. Should `B008_po_money_gate` remain STOP until full physical-stock drift is solved, or is there a reviewed substitute stock/capital-risk contract that would allow a separate YELLOW-to-GREEN proof?

Please answer with a strict gate:

- `GREEN_TO_CONTINUE_NONPRODUCTION_REPAIR` if the copied-temp closure/adapter is valid and the next route can continue without production authority.
- `YELLOW_NEEDS_CONTRACT_PATCH` if the route is directionally correct but requires a source-contract or validator-contract patch.
- `RED_DO_NOT_USE` if the proof or adapter is unsafe.

Do not approve production preflight or production apply unless you explicitly state a separate exact production authorization requirement.
