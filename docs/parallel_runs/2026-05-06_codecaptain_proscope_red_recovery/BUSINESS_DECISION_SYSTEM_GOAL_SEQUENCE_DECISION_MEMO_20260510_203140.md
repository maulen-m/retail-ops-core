# Business Decision System Goal Sequence Decision Memo

Generated: `2026-05-10T20:31:40+0500`

Status: `READY_FOR_CODECAPTAIN_REEVALUATION`

Gate: `GREEN_REVIEW_ONLY_SEQUENCE_DOCUMENTED`

## Purpose

This memo preserves the bigger-goal sequence after the accepted Cash Risk Daily validate-only proof, so future agents can see where the business-decision system stands, why it is not yet fully live, and which next goals are safe.

This is an internal planning and review artifact. It does not authorize owner publication, owner send, production apply, scheduler automation, DB/workbook mutation, cash movement, PO commitment, ad spend, price/stock changes, or external-system writes.

## Current State

Current active status:

`CASH_RISK_DAILY_OPERATOR_REVIEW_SURFACE_READY`

Current business-decision grade:

`6.5 / 10`

Interpretation:

We have a validated review-only Cash Risk Daily decision-support surface. We do not yet have a fully functional live business decision system because owner-publication, scheduler, production, cash, PO, ad-spend, price/stock, workbook, and external-write authority remain blocked.

## Why 6.5 / 10

Strengths:

- Cash Risk Daily copied-DB validate-only proof completed `GREEN`.
- CodeCaptain accepted the proof for review-only use with token `GREEN_ACCEPT_CASH_RISK_DAILY_VALIDATE_ONLY_PROOF`.
- Validator matrix is `7/7 PASS`.
- Trust banner is `GREEN`.
- Operator review surface is ready.
- Warning cohorts remain visible instead of hidden: `23` product-identity quarantine rows and `252` header-only source-gap rows.
- Blocked decisions are explicit and preserved.

Limits:

- Operator has not yet accepted the review surface.
- `ADS_SOURCE_STALE` remains visible.
- Ads-dependent claims, profit-after-ads claims, ad-spend decisions, and owner-publication claims remain blocked without a separate source-freshness decision.
- Current authority is review-only, not production, scheduler, owner-publication, or external-write authority.
- The surface is not yet a recurring live operating loop.

## Phase Ladder

| Phase | Target state | Current grade band | Current state |
|---:|---|---:|---|
| `0` | No trusted decision chain | `0.0-1.0` | Superseded |
| `1` | Evidence inventory and boundary awareness | `1.0-2.5` | Superseded |
| `2` | Current-boundary validate-only plan | `2.5-4.0` | Superseded |
| `3` | Guarded validate-only runner contract | `4.0-5.0` | Complete |
| `4` | Copied-DB proof with validators and trust banner | `5.0-6.0` | Complete |
| `5` | Operator review surface with warnings and blocked decisions | `6.0-7.0` | Current |
| `6` | Owner-publication readiness delta reviewed | `7.0-7.5` | Next recommended |
| `7` | Fresh source proof, especially ads freshness, rerun cleanly | `7.5-8.2` | Pending |
| `8` | Scheduler design-only contract, dry-run default, no live enablement | `8.2-8.8` | Pending |
| `9` | Backup-first gated production apply and owner-safe output flow | `8.8-9.5` | Pending separate authorization |
| `10` | Fully functional business-decision system with recurring safe ops | `9.5-10.0` | Final goal |

## Current Issues

1. `operator_review_surface_not_yet_accepted`
2. `owner_publication_scheduler_production_external_writes_require_separate_authorization`
3. `ADS_SOURCE_STALE`
4. `23` product-identity quarantine rows must remain warnings and must not be treated as product truth.
5. `252` header-only source-gap rows must remain evidence-only and must not be inserted/productized.
6. Current proof is copied-DB validate-only; it is not authority to mutate `db/app.db` or `excel_ui/SALES_KSP_CRM_V3.xlsx`.
7. Scheduler automation and LaunchAgent/plist changes remain forbidden.
8. Owner approval request, owner send, old phrase reuse, and Agent64 activation remain forbidden.

## Safe Next-Goal Options

Option `1` - Recommended: owner-publication readiness delta.

Goal:

Define exactly what is missing before the review-only Cash Risk Daily surface can be considered for owner-facing publication.

Output:

- A review-only delta memo.
- Exact owner-safe wording constraints.
- Exact missing evidence list.
- Explicit claims that remain blocked.
- Decision tokens for CodeCaptain review.

Why first:

This is the lowest-risk bridge from review-only evidence to business-facing use. It does not mutate production or ask the owner for approval.

Option `2` - Fresh copied-DB proof refresh.

Goal:

Refresh stale source inputs, especially ads source freshness, then rerun copied-DB validate-only proof.

Output:

- New evidence folder.
- New validator matrix.
- New trust banner.
- Updated warning cohort proof.
- CodeCaptain review pack.

Why second:

This can improve owner-publication readiness, especially if `ADS_SOURCE_STALE` is removed or reclassified.

Option `3` - Decision-surface hardening.

Goal:

Convert the operator review surface into a repeatable template with stable acceptance checklist, safe/unsafe claim table, and machine-readable gate fields.

Output:

- Durable surface template.
- JSON status schema or phase map.
- Regression checks if practical.

Why useful:

It makes future runs faster and reduces human memory load.

Option `4` - Scheduler design-only lane.

Goal:

Draft the automation contract without enabling it.

Output:

- Dry-run-default scheduler design.
- Proof-window lock behavior.
- Backup-first and rollback requirements.
- Explicit apply gates.

Why not first:

Automation before owner-publication readiness risks building a faster path around still-blocked decisions.

Option `5` - Production/live lane later.

Goal:

Only after owner-publication readiness and fresh proof are accepted, evaluate backup-first production apply, owner-safe output, and recurring operations.

Output:

- Separate authorization request.
- Backup and rollback proof.
- Production DB/workbook boundary proof.
- External-write and scheduler gates.

Why later:

This is the high-blast-radius lane and must not be opened from the current review-only state.

## Recommended Sequence

1. CodeCaptain reevaluates this goal sequence and either accepts, amends, or blocks it.
2. If accepted, operator accepts or amends the Cash Risk Daily operator review surface.
3. Run Option `1`: owner-publication readiness delta, review-only.
4. Run Option `2`: fresh copied-DB proof refresh if the delta requires fresher source truth.
5. Run Option `3` in parallel or after Option `1` if template hardening is useful.
6. Only after owner-publication readiness and source freshness are clean, consider Option `4` scheduler design-only.
7. Only after a separate explicit authorization lane, consider Option `5` production/live work.

## CodeCaptain Reevaluation Question

Please review whether this sequence is safe and sufficient as the controlling project roadmap for the next phase after `CASH_RISK_DAILY_OPERATOR_REVIEW_SURFACE_READY`.

Return exactly one decision token:

- `GREEN_ACCEPT_BUSINESS_DECISION_SYSTEM_SEQUENCE`
- `YELLOW_AMEND_SEQUENCE_BEFORE_NEXT_LANE`
- `RED_DO_NOT_USE_SEQUENCE`

If `YELLOW` or `RED`, state the minimum required amendment before the next lane.

## Not Authorized By This Memo

- owner-publication GREEN
- owner send
- owner approval request
- scheduler automation
- LaunchAgent or plist mutation
- production `db/app.db` write
- protected workbook write
- Kaspi, Google, ads platform, bank, browser, Web_automation, or external-system write
- cash movement
- supplier payment
- PO commitment
- ad spend
- price or stock change
- production apply
- old phrase reuse
- Agent64 activation
