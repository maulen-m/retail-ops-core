# PHASE39_VALIDATOR_ROUTE_MATRIX

Status: `YELLOW_VALIDATOR_ROUTES_READY`
Created: `2026-05-22`
Evidence root: `exports/validation/mvos_phase39_validator_route_matrix/20260522_060816`

This is a non-production execution-routing artifact. It converts the current Phase38 decision queue into concrete validator routes for future copied-temp agents and CodeCaptain review. It does not authorize production DB writes, workbook writes, source-pointer writes, scheduler/LaunchAgent/cron changes, Web_automation writes, Kaspi/API/WebUI mutations, external writes, ad-platform writes, ad spend, stock changes, price changes, cash movement, PO commitment, owner publication, production preflight, or production apply.

## Current Review Pack

Primary Phase38 addendum pack:

`~/Docs/Oracle/Autonomous_business/2026-05-22/060611_TASK-000_mvos-phase38-decision-addendum-codecaptain`

Primary routing document:

`~/Docs/Autonomous_business/docs/parallel_runs/2026-05-22_mvos_phase38_decision_approval_queue/PHASE38_DECISION_APPROVAL_QUEUE.md`

## Validator Route Rules

- Run validator matrices on copied DBs unless a command is explicitly read-only against source files.
- Never use a validator pass on a narrow copied-temp scope as owner-publication or production-preflight authority.
- Keep source-freshness, policy-gate, and production-apply gates separate.
- Do not create fake zero events, fake zero ads spend, synthetic order entries, inferred physical stock, or inferred COGS authority.
- Preserve owner facts: Universal offer `132822924_328581041` maps to `CL_NEW-CLO_MEN_LEG_WHITE` for copied-temp planning only, and no fresher physical stock data exists than the last source already used.

## Route Matrix

| Route | Blockers | Current state | Validator command template | Expected current result | Green requires |
| --- | --- | --- | --- | --- | --- |
| `R_ads_source_truth` | `B001a`, `B002a`, part of `B002c` | Retained. No accepted current Meta/Kaspi Marketing source packets for the current boundary; STOREB May18 positive spend remains visible; ACMEWEAR LINE31 Starry Black lacks exact ads row or zero/no-campaign proof. | `python3 scripts/validate_ads_source_packet_contract.py --manifest <accepted_packet_manifest> --require-existing-files --json --strict`; then `python3 scripts/validate_ads_sidecar_readiness.py --db <copied_db> --as-of 2026-05-22 --output-root <evidence_root> --strict`; then `python3 scripts/validate_policy_source_freshness.py --db <copied_db> --as-of 2026-05-22 --strict --json` | YELLOW/BLOCKED until accepted current packets or zero/no-campaign proof exists. | Accepted current packet manifests, sidecar readiness, and C3 ads source rows clear without zeroing retained spend. |
| `R_cashflow_truth` | `B001b`, `B002b`, part of `B002c` | Partially proven in copied DB. Daily reaches `2026-05-22`; events reach `2026-05-21`; same-day event-table rule still blocks. | `python3 scripts/validate_cashflow_invariants.py --db <copied_db>`; `python3 scripts/validate_order_cashflow_coverage.py --db <copied_db> --as-of 2026-05-22 --strict --json`; `python3 scripts/validate_policy_source_freshness.py --db <copied_db> --as-of 2026-05-22 --strict --json`; `python3 scripts/validate_policy_gate_results.py --db <copied_db> --strict --json` | YELLOW/BLOCKED until CodeCaptain accepts no-eligible-event-day contract or real May22 event evidence exists. | Cashflow invariants, strict order coverage, source freshness, and policy gates pass under reviewed contract/source evidence. |
| `R_order_entry_identity` | `B001c`, `B004` | Copied-temp closed, production blocked. No-real-entry quarantine retained for Universal `922898360` and `923528055`. | `python3 scripts/validate_order_entries_freshness.py --db <copied_db> --as-of 2026-05-22 --lookback-days 14 --stores STOREB,ACMEWEAR,UNIVERSAL --output-root <evidence_root> --strict` | Expected copied-temp pass only under retained quarantine contract. | CodeCaptain accepts retained no-real-entry contract or real item-entry evidence exists; no synthetic rows. |
| `R_status_lifecycle` | `B001d`, `R012` | Retained. Scoped ledger passes `2026-05-05..2026-05-17` but fails through `2026-05-18`; day-complete two rows close in copied-temp only. | `python3 scripts/validate_status_ledger_continuity.py --ledger-root <ledger_root> --start 2026-05-05 --end 2026-05-18 --stores-config <stores_config> --strict`; `python3 scripts/validate_day_complete.py --cutoff-date 2026-05-18 --db-path <copied_db>`; then C3 source/gate validators on copied DB. | YELLOW/BLOCKED for current required window. | Exact same-window ArchiveOrders/status ledger through `2026-05-18` or reviewed scoped/dated contract; day-complete remains copied-temp until reviewed write lane. |
| `R_sales_truth` | `B001e`, sales side of `B004`/`B005` | Copied-temp closed with owner-confirmed Universal identity, but production/source gates still block. | `python3 scripts/validate_sales_vs_workbook_anchor.py --db <copied_db> --as-of 2026-05-22`; strict sales rebuild command from the accepted copied-temp integrator run; then C3 source/gate validators. | Expected copied-temp pass for anchor/identity, but C3 may remain blocked. | Strict sales rebuild and source gates pass under accepted source contracts; no production apply from this route. |
| `R_stock_physical_truth` | `B001f`, `B002d`, `B003` | Retained. No fresher physical stock source exists per owner; offer availability cannot clear physical stock truth. | There is no current `scripts/validate_inventory_snapshot_freshness.py` file. Use `python3 scripts/validate_policy_source_freshness.py --db <copied_db> --as-of 2026-05-22 --strict --json`, `python3 scripts/validate_policy_gate_results.py --db <copied_db> --strict --json`, `python3 scripts/validate_inventory_cost_drift.py --db <copied_db> --as-of 2026-05-22`, and `python3 scripts/validate_po_dashboard_invariants.py --db <copied_db>` for the available concrete gates. | YELLOW/BLOCKED until fresh physical stock authority or CodeCaptain substitute contract exists. | Fresh physical-stock source, or reviewed substitute stock/capital-risk contract that explicitly keeps affected stock/PO outputs blocked or warning-visible. |
| `R_single_truth_po_money` | `B006`, `B007`, `B008` | Single-truth system copied-temp closed under declared scope; alignment/PO money still blocked by physical-stock drift. | `python3 scripts/validate_single_truth_system.py --db <copied_db> --xlsx <inbound_workbook> --dashboard <dashboard_json> --po-part-scope-contract <contract_tsv>`; `python3 scripts/validate_single_truth_alignment.py --db <copied_db> --input <dashboard_json>`; `python3 scripts/validate_po_money_gate.py --db <copied_db> --inbound-workbook <xlsx> --as-of 2026-05-22 --json --allow-accepted-shortages-for-copied-temp --po-part-scope-contract <contract_tsv> --unit-cogs-evidence-csv <csv> --single-truth-alignment-input <dashboard_json>` | YELLOW/BLOCKED because physical-stock drift remains. | Alignment and PO money pass without hiding stock drift, or CodeCaptain accepts an explicit substitute/capital-risk contract. |
| `R_exception_queue` | `B009` | Retained high-stock exceptions visible. | `python3 scripts/validate_exception_queue_db.py --db <copied_db> --strict --json` | Expected visible retained exceptions, not green unless accepted. | Zero unaccepted exceptions or reviewed visible-retained exception contract. |
| `R_dirty_repo` | `B010` | Production stopline. Phase37 measured `374` status entries. | `git status --porcelain=v1 -uall`; `git diff --name-status`; `bash scripts/check_no_db_tracked.sh` | YELLOW/STOP for production. | Logical commit/park split after CodeCaptain boundary review; no unrelated changes reverted. |
| `R_automation_boundary` | `B011` | Paused until owner resumes. | Future only: `python3 scripts/manage_business_automation.py status`; `python3 scripts/manage_business_automation.py verify --expect paused --scope all-business`; scheduler heartbeat only after approved resume. | STOP until owner names resume scope. | Exact owner-approved resume plus status/heartbeat proof. |
| `R_daily_autonomy_B012` | `B012` | Improved but retained. Final on-delivery residual is `ACMEWEAR 929183530 / LINE-31-LS_2XL`; identity proven, COGS authority missing. | `python3 scripts/validate_cogs_integrity.py --db <copied_db> --as-of 2026-05-22 --unit-cogs-evidence-csv <csv>`; `python3 scripts/validate_cogs_completeness_by_month.py --db-path <copied_db> --as-of 2026-05-22 --unit-cogs-evidence-csv <csv> --childsum-cogs-evidence-csv <csv> --strict`; `python3 scripts/validate_dim_sku_light_alignment.py --db <copied_db> --xlsx <xlsx>`; `python3 scripts/validate_on_delivery_freeze.py --db <copied_db> --until 2026-05-22`; `python3 scripts/validate_drift_pack_slo.py --output-root <drift_pack_root> --as-of 2026-05-22 --strict` | YELLOW until LINE-31-LS COGS authority and repeated-run/default route are accepted. | Owner-approved copied-temp COGS or ChildSum COGS plus repeated-run/default-route matrix accepted by CodeCaptain. |

## Concrete Next Agent Slices

If execution agents are used after CodeCaptain or optional owner approval, keep the write sets disjoint:

| Agent slice | Purpose | Writes allowed |
| --- | --- | --- |
| `A_CodeCaptain_ingest` | Read CodeCaptain answer from pack `Answer/`, classify accepted/rejected contracts, and update local routing docs. | Local docs/evidence only. |
| `B_Source_acquisition_if_approved` | Only if exact owner approval is given, fetch/read current ads or status source evidence and write immutable local packets. | Local evidence only; no external writes or mutations. |
| `C_Copied_temp_integrator` | Materialize only accepted contracts into a copied DB and run the validator matrix. | Copied DB and local evidence only. |
| `D_Dirty_split_planner` | Prepare commit/park review plan after CodeCaptain boundary is accepted. | Local docs only; no commit/stage/revert unless later approved. |

## Gate

`YELLOW_VALIDATOR_ROUTES_READY`

Reason: this phase removes ambiguity in validator routing and identifies a stale/missing validator command reference, but it does not clear retained source/authority blockers.
