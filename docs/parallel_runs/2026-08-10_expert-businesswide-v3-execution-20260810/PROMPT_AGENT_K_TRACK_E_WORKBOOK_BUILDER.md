# Agent K - Track E Owner Count Workbook Builder

Effort pin: `low`.

## Objective

Implement and generate the missing read-only Track E owner count workbook for
exactly T-SHIRT/BERSERK mixed, NIKE-SHIRT, and slow LINE51. The workbook is an
owner-entry evidence artifact only. It must not alter any production workbook,
database, stock, offer, price, campaign, cash, scheduler, Telegram, supplier,
CRM, or external system.

## Authority And Inputs

- Read repo `AGENTS.md` and the ratified V3 plan first.
- Primary analysis input:
  `~/Docs/Autonomous_business_agent_handoffs/2026-08-10_expert-businesswide-v3-execution-20260810/agent_f_report.md`.
- Source databases and historical files are read-only. Missing source facts
  remain blank and `UNKNOWN/STOP`; never infer or coerce them to zero.
- Current estimates are entry guidance, not owner-approved physical truth.

## Write Scope

You may create or edit only:

- `scripts/build_track_e_owner_count_workbook.py`
- `tests/test_build_track_e_owner_count_workbook.py`
- local-only immutable outputs under
  `~/Docs/Autonomous_business_agent_handoffs/2026-08-10_expert-businesswide-v3-execution-20260810/track_e_owner_count_workbook_<timestamp>/`
- your closeout at
  `~/Docs/Autonomous_business_agent_handoffs/2026-08-10_expert-businesswide-v3-execution-20260810/TRACK_E_OWNER_COUNT_WORKBOOK_CLOSEOUT.md`

Do not edit `.claude` files, status boards, completion matrices, ledgers, any
other script/test, or Git index state. Do not commit, push, stash, clean,
revert, checkout, or reset.

## Tests First

1. Add focused tests and run them before production code exists. Capture the
   intended RED output in the timestamped output folder.
2. Tests must prove:
   - explicit numeric `0` is preserved as a valid owner correction;
   - blank correction preserves an exact estimate, while a range remains a
     range and is never replaced by its midpoint;
   - missing identity, COGS, reserve, or movement evidence keeps approved lot
     quantity and economics blank with `UNKNOWN/STOP`;
   - only the three authorized candidate lanes exist;
   - LINE51 4XL estimate may be zero without being treated as blank;
   - formula cells and data validations never authorize outreach;
   - generation is deterministic except for an explicit as-of field.

## Workbook Contract

Create an `.xlsx` with these sheets:

- `README`
- `COUNT_ENTRY`
- `REPLAY_AND_GAPS`
- `COGS_AND_FLOORS`
- `LOT_PREVIEW`

Use one row per known or unresolved physical pool x color x size. Include the
identity, count evidence, stock state, movement replay, COGS, channel economics,
offer-gate, and prepaid/non-consignment columns defined in `agent_f_report.md`.
Owner-editable cells must be visually distinct and unlocked where supported;
formula/evidence cells must be visibly read-only. Include clear `UNKNOWN/STOP`
states, source references, and Asia/Almaty timestamps. No row may claim an
approved lot or outreach authority before exact count, reserve, landed COGS,
three prices, prepaid/non-consignment confirmations, and owner approval exist.

Builder interface:

```text
--as-of <ISO8601+05>
--strict
--output-dir <DIR>
```

It must have no apply mode and make no external calls. Emit sanitized CSV/JSON
mirrors plus SHA-256 manifest beside the workbook. Reopen the workbook and
mirrors during verification.

## Verification

- Focused tests pass.
- `py_compile` passes.
- Workbook reopens with expected sheets, formulas, validations, freeze panes,
  widths, and no external links/macros.
- Output manifest hashes verify.
- Secret/PII scan passes.
- Report exact paths, counts, test commands, gaps, and `external_writes=0`.

## Stop Points

- STOP if a source conflict cannot be represented as a range or explicit gap.
- STOP before any production workbook/DB/pointer/scheduler/external write.
- STOP before any outreach, inventory reservation, public quantity, or owner
  approval claim.
- STOP if unrelated dirty files would need to be modified.
