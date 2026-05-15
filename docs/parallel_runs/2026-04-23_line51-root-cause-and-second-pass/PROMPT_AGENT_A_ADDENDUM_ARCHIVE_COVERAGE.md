# PROMPT_AGENT_A_ADDENDUM_ARCHIVE_COVERAGE — Add Archive Coverage Audit To Second-Pass Bundle

This is a bounded addendum to:

- `~/Docs/Autonomous_business/docs/parallel_runs/2026-04-23_line51-root-cause-and-second-pass/PROMPT_AGENT_A.md`

Use it only as an extension of that prompt, not as a new broad rollout.

## Why This Addendum Exists

Direct review of the exact external pack showed:

- `ArchiveOrders_WEBUI_MERGED_ALL_STORES.csv` is broadly present through `2026-04-22`
- the March/April problem is not mainly “missing whole days”
- but the tail is a mixed-source regime:
  - full WebUI parse through `2026-03-05`
  - delta through `2026-03-19`
  - hybrid tail through `2026-04-22`
- `db_orders_tail_2026-04-23.csv` is thin
- returns and cancellations exist in the archive, but stock-state interpretation is still risky

That means the external expert should receive an explicit archive-coverage audit so he does not have to infer source confidence from raw files.

## Add One More Deliverable Set

Inside:

- `~/Docs/Autonomous_business_agent_handoffs/2026-04-23_line51-root-cause-and-second-pass/`

add:

1. `archive_coverage_audit_2026-04-23.md`
2. `archive_coverage_by_day_store_status_2026-04-23.csv`

## What The Audit Must Show

At minimum, document:

1. archive source regime by period:
   - full parse
   - delta
   - hybrid tail
   - DB tail supplement
2. date coverage:
   - min and max `status_change_at`
   - whether rows exist continuously through the relevant window
3. by-day / by-store / by-status counts for at least:
   - `DELIVERED`
   - `RETURNED`
   - `CANCELLED`
   - `SHIPPED`
   - `READY`
   - `ACCEPTED`
4. explicit warning that:
   - returns are present in the archive
   - cancellations are present in the archive
   - but active-stock semantics still require the quarantine contract, not raw archive status alone
5. the thinness of `db_orders_tail_2026-04-23.csv`

## Required Interpretation

The markdown audit should answer this clearly:

- the external pack is **not** mainly missing March/April days
- the bigger risk is mixed-source tail quality and stock-state interpretation
- therefore the second-pass expert should focus on:
  - quarantine treatment
  - cancellation semantics
  - family-specific root causes
  - not on inventing a blanket missing-days correction

## Update The Expert Bundle

Update the corrected external second-pass context so it explicitly includes:

- `archive_coverage_audit_2026-04-23.md`
- `archive_coverage_by_day_store_status_2026-04-23.csv`

And revise the external-expert prompt/checklist so it states:

- archive day coverage is broadly present through `2026-04-22`
- `2026-04-23` is only thin DB-tail support
- tail quality is mixed-source
- returns/cancellations are present, but active-stock interpretation must use the quarantine-aware contract

## Constraints

- Keep this read-only / export-only if possible.
- Do not reopen broad sales-truth repair in this addendum.
- Do not turn this into another stock rebuild.
- This is an evidence sidecar so the next external pass has cleaner context.

## Validation

If you only add read-only handoff exports and spec updates:

- `scripts/check_no_db_tracked.sh`
- `scripts/lint_docs.sh` if markdown/spec files changed

Record inherited broader repo red gates as inherited stoplines; do not rerun unrelated heavy gates for ceremony.
