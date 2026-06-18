# Temporary OCR Stock Override Decision - 2026-06-16

Status: OWNER_APPROVED_TEMPORARY_OPERATIONAL_OVERRIDE

Owner approval source: chat approval on 2026-06-16.

## Decision

Use the approved warehouse OCR/manual stock count surfaces as the temporary
priority layer for day-to-day sales and archive-to-active stock decisions while
the main orchestrator/refactor agent is rebuilding the durable single source of
truth in a separate worktree.

This temporary layer exists to reduce operational conflict while refactoring is
in progress:

- avoid activating marketplace offers when the temporary stock layer says stock
  is zero, negative, parked, or mapping-pending;
- allow activation decisions when the temporary report says stock is positive;
- preserve absent OCR/manual cells as "not captured", not zero;
- apply addition rows as additive restored/canceled-return units when the source
  says addition;
- apply full/supersede rows as replacement snapshots for the covered SKU-size or
  stock pool only;
- park mapping-flagged OCR rows until product identity is proven.

## Owner Conflict Holds

On 2026-06-16, the owner challenged the temporary Line52 XL result because the
human/OCR understanding is approximately 13 total warehouse units, not an
old-ledger balance above 100 plus a June 11 addition. Until a newer
owner-approved correction or the main refactor supersedes this temporary layer,
`CL_OC_MEN_LINE52_BLACK_XL` must be treated as:

`OWNER_CONFLICT_HOLD_DO_NOT_ACTIVATE_PENDING_RECOUNT`

The report should keep the computed stock visible for diagnosis, but activation
agents must not activate this row from the temporary report.

## Supersession

This is not intended to be the final architecture. When the main refactor returns
to the main Autonomous_business/Web_automation worktrees with conflict-free,
up-to-date single-source stock truth, it is fully acceptable for that refactor
result to supersede this temporary override.

Supersession policy key:

`future_main_refactor_results_may_override_this_temporary_owner_approved_stock_layer`

## Activation-Agent Handoff

Parallel marketplace activation agents should read:

`exports/current/temporary_ocr_stock_override/temporary_stock_decision_latest.csv`

Activate only rows whose `activation_recommendation` begins with
`ACTIVATE_OK_POSITIVE`. Do not activate rows marked zero, negative, parked, or
mapping-pending from this report unless a newer owner-approved source explicitly
supersedes it.

## Boundaries

This decision authorizes the Autonomous_business DB stock override materializer
and report generation. It does not directly authorize this script to write to
Kaspi merchant cabinets, Web_automation marketplace state, or external systems.
