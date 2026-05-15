# Operational Decision Policy V1

Status: active C2 policy contract

Machine-readable policy: `config/operational_decision_policy.yaml`

Owner QA evidence: `docs/parallel_runs/2026-05-03_operational-stock-truth-system/OWNER_QA_OPTION_C_INPUTS_20260503_203849_ALMT.md`

Do not copy secrets into this document. Credentials, API tokens, passwords, cookies, and sessions must stay in env files or external secret stores; docs and tests may reference env var names only.

## Purpose

This contract defines the fail-closed operating policy for deciding whether stock, profit, cashflow, purchase orders, inbounds, marketing costs, and reorder decisions are decision-grade.

It intentionally avoids embedding fragile implementation details. Mutable thresholds live in `config/operational_decision_policy.yaml`; source formulas remain in their owning docs.

## Authority Boundaries

- Inventory formulas and capital caps: `docs/inventory/Master_Inventory_Rules_v9.md`.
- PO algorithm: `docs/protocol/active/PO_making_logic_v3.md`.
- Data model: `docs/inventory/Sales_Data_Model_V16.md`.
- Daily ops workflow: `docs/ops/KASPI_DAILY_OPS_WORKFLOW_CONTRACT.md`.
- Stock snapshot operations: `docs/ops/STOCK_SNAPSHOT_RUNBOOK.md`.
- This policy owns operational thresholds, publication gates, and manual review ownership.

If this policy conflicts with a formula owner, update the formula owner first, then update this policy/config.

## Recommended Path

Use C2 first, then C3.

C2 means this active policy doc plus a YAML config and executable tests. It is the fastest durable path because agents and scripts can consume the policy immediately without waiting for a full policy registry.

C3 means promoting the same policy into an effective-dated DB registry with daily exception queues, previous-version rollback, and UI/report consumption from DB only. C3 should not replace the C2 contract; it should ingest it.

## Fail-Closed Rule

If a required input is missing, stale, contradictory, or not covered by a deterministic source, the system must stop publication or mark the affected decision as non-decision-grade.

Do not publish best-effort green states for:

- current stock,
- profit after ads,
- reorder recommendations,
- purchase approvals,
- cashflow green status,
- active sellable returns stock.

## Current Owner Truth Baseline

- Active Kaspi stores with positive stock on sale: `ACMEWEAR`, `UNIVERSAL`, `STOREB`.
- Inactive stores: `11KZ`, `MELVIS`.
- Active Kaspi internal ads stores requiring coverage: `ACMEWEAR`, `STOREB`.
- STOREB marketing can currently be accessed through the Universal marketing cabinet store switcher.
- Meta/Facebook funnel evidence applies to the `ACMEWEAR` Kaspi store. `STOREB` marketing is Kaspi-internal marketing evidence, not Meta/Facebook evidence.
- Pending orders do not reduce stock.
- Dispatched or shipped orders reduce stock.
- Delivered orders remain sold.
- Cancelled orders do not reduce stock unless already shipped and explicitly reversed.
- Returned products increase active stock only after QC acceptance.
- Unknown COGS blocks profit publication.
- Missing required ads data blocks profit publication.
- Minimum owner cash reserve is `1,500,000 KZT`.

## Stock Anchor And Adjustment Rule

The current best stock anchor is:

`~/Docs/Oracle/Autonomous_business/2026-04-24/103302_TASK-000_line51-root-cause-external-second-pass-2026-04-24/expert_answer/24.4.2026/second_pass_stock_value_evaluation_2026-04-24.xlsx`

Before rebuilding current stock from subsequent events, apply the required `20%` proportional LINE51 stock decrease to the baseline unless a later approved implementation records that adjustment in a better effective-dated ledger layer.

Negative active stock values must be normalized to zero and surfaced as exceptions because unprocessed collected returns/cancels are quarantine stock, not active sellable stock.

Accepted active controls remain visible in C3 exception reporting but do not block global owner publication by themselves. This applies to owner-approved active-zero holds, owner-approved no-double-reduce controls, the Line61 4XL exclusion, and the scoped Berserk Rush negative raw balance rows where owner truth says active sellable stock is `0` and returned/cancelled stock stays quarantined until employee QC acceptance.

Unresolved high-severity exceptions that are not covered by an accepted active-control rule remain publication blockers.

## Decision Thresholds

The executable thresholds are in `config/operational_decision_policy.yaml`.

High-level defaults:

- Kaspi orders and order-status events must be fresh within `24` hours.
- Required Kaspi internal ads stores must have ads data fresh within `24` hours.
- Bank balances must be manually reviewed at least weekly until automated.
- Stock and PO unit reconciliation tolerance is zero units.
- Unknown COGS blocks profit publication.
- Missing required ads blocks profit publication.
- Unmapped SKU rows with at most two sales may be ignored only with the configured ignored label; above that cap they are quarantined and block publication.
- Reorder and new-product decisions must preserve the owner cash reserve and Master Inventory Rules v9 capital caps.

## Manual Review Ownership

- Business owner reviews the daily exception queue every business day.
- Business owner owns SKU merges, stock overrides, supplier obligations, cargo payment obligations, cash-reserve exceptions, and any waiver request.
- Warehouse employee owns return QC acceptance and received-quantity confirmation.
- Agents may auto-repair deterministic source fetches, schema-safe mappings, and generated sidecars only when tests or validation gates prove the repair.
- Agents may not override publication gates.

## C3 Migration Requirements

The robust version should promote this YAML policy into an effective-dated DB policy registry.

Before C3 is green:

- every active policy value has an effective date and owner,
- scripts read active policy from DB,
- YAML remains a bootstrap/contract source,
- validators compare DB policy to this contract,
- daily exception queues assign owners from policy,
- rollback can restore the prior active policy version without data loss.
