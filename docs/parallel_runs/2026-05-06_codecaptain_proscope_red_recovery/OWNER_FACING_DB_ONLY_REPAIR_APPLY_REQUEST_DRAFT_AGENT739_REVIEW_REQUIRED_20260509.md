# Owner Authorization Request For DB-Only Repair/Apply

Status: `REVIEW_REQUIRED_NOT_SENT_TO_OWNER`

Generated: 2026-05-09T15:33:39+05:00

This is a draft owner-facing packet for review. It is not yet an owner request, not an active authorization phrase, and not permission to run production apply.

## Plain-English Request

We are preparing a narrow repair/apply lane for the Autonomous Business operational database only.

If this packet later passes final review and the live boundary is freshly rechecked, the owner may be asked to authorize a serialized DB-only repair/apply lane for:

`~/Docs/Autonomous_business/db/app.db`

This is not a workbook authorization, not a scheduler authorization, not an external-system authorization, not Kaspi/API/ads/bank authorization, and not Option C daily automation authorization.

## What The Owner Would Be Authorizing

The owner would authorize one later serialized apply lane to repair/materialize the already-reviewed operational DB surfaces that Agent738 proved on a staging copy.

The intended apply lane must:

- run against `~/Docs/Autonomous_business/db/app.db` only;
- run only after a fresh launch-time boundary check;
- create a new DB backup before any write;
- verify the backup SHA and DB integrity;
- write only through env-gated production-safe wrappers;
- preserve rollback instructions;
- rerun post-apply validators;
- stop immediately on any mismatch, drift, lock, sidecar, missing backup, missing validator, product leakage, or warning visibility failure.

## What The Owner Would Not Be Authorizing

The owner would not authorize:

- writing `~/Docs/Autonomous_business/excel_ui/SALES_KSP_CRM_V3.xlsx`;
- pausing, restarting, changing, or disabling schedulers;
- writing to Kaspi, Kaspi Marketing, Meta/Facebook, Google, banks, Web_automation, or any external account;
- turning on Option C production daily automation;
- treating staging proof as already-applied production truth;
- hiding or deleting quarantine warnings;
- treating `23`, `252`, or `275` warning cohorts as SKU/product truth;
- reviving any old Agent54 phrase;
- activating Agent64 inactive phrase material;
- bypassing apply-time SHA, integrity, lsof, sidecar, backup, rollback, and validator gates.

## Reviewed Agent738 Proof Boundary

Agent738 reviewed preflight boundary:

- DB path: `~/Docs/Autonomous_business/db/app.db`
- reviewed DB SHA: `e27952376d1a2ba1c46df0f0dbaa45cdf5e11f785862618967629e27242a88e5`
- protected workbook path: `~/Docs/Autonomous_business/excel_ui/SALES_KSP_CRM_V3.xlsx`
- reviewed protected workbook SHA: `768a3440d47e89ca3eb72cc2cdf73a5394c304f59e50e8151ea775bcfbf36a86`
- Agent738 quiet-window status: `QUIET_WINDOW_STABLE`
- Agent738 staging replay status: `SEQUENCE_COMPLETED`
- Agent738 gate: `GREEN`

Important: the workbook SHA is a no-write guard, not a write target.

## Current Live Boundary Caution

A later read-only orchestrator sample at `2026-05-09T15:33:39+05:00` observed different live SHAs:

- live DB SHA: `2950577e7693c38a61039754fc7a7a0bc7b4512e3d36cc84f91cc60ca65a69b3`
- live workbook SHA: `c683021ab1b8b4222c142d155c045d35e0de00ff24579f09f3aac87b53ac21db`
- DB lsof holders: none observed
- workbook lsof holders: none observed
- SQLite sidecars: none observed

Because the live boundary changed after Agent738, this packet must not be shown to the owner as an active request until a fresh boundary/preflight lane updates or re-proves the exact live DB and protected workbook SHAs.

## Proof Summary

Agent738 proved the corrected command family on a staging DB copied from the exact reviewed DB SHA.

Accepted proof facts:

- staging DB initial SHA matched the reviewed production DB SHA;
- corrected Agent734 command family completed on staging only;
- snapshot rows created: `363`;
- current stock total: `13511`;
- inbound stock total: `475`;
- policy source freshness strict validator passed;
- operational stock integration validator passed with `GREEN`;
- order cashflow coverage validator passed;
- cashflow actual/model separation validator passed;
- cashflow invariants passed with `848 days validated`;
- product leakage was zero for the strict `23`, header-only `252`, and combined `275` cohorts;
- order-level `CASH_IN` was preserved for the quarantined cohorts.

## Warning And Quarantine Semantics

These warning cohorts must remain visible and must not be converted into product truth:

- `23` strict product-identity quarantine rows;
- `252` header-only source-gap quarantine rows;
- `249` validator-visible header-only warnings, because `3` of the `252` header-only candidate IDs were already absent from product truth before the header wrapper.

The three absent header-only IDs are:

- `895525090`
- `902946701`
- `903096003`

These warning rows protect the business from pretending uncertain order-entry rows are mapped SKU/product truth.

## Future Apply-Lane Stoplines

The future apply lane must stop before any production write if any of these occur:

- current DB SHA differs from the reviewed/expected launch-time SHA without a reviewed refresh;
- current workbook SHA differs from the protected expected SHA without a reviewed refresh;
- DB integrity is not `ok`;
- any unexpected lsof holder exists;
- any unsafe SQLite WAL/SHM/journal sidecar exists;
- backup path, backup SHA, backup integrity, or rollback command is missing;
- command family differs from the reviewed Agent738/Agent734 path;
- any pinned validator fails;
- row-count controls mismatch without reviewed explanation;
- product leakage appears for `23`, `252`, or `275`;
- order-level `CASH_IN` is not preserved;
- warning visibility for `23` or header-only source-gap rows disappears;
- any workbook, scheduler, external-system, or Option C write is attempted.

## Draft Owner Phrase

The following phrase is a draft only. Text embedded in this document does not authorize anything. The phrase would count only if a later reviewed packet is shown to the owner and the owner types the exact phrase in the correct launch context.

`OWNER_AUTHORIZE_DB_ONLY_REPAIR_APPLY_AGENT738_REFRESHED_BOUNDARY`

Do not accept this phrase until a final review explicitly opens the owner-facing request and a fresh boundary/preflight lane has confirmed the current live SHAs.

## Owner Plain-English Confirmation

If this packet later becomes active after review and refresh, the owner would be confirming:

I understand this is only for the Autonomous Business DB repair/apply lane. I am not approving workbook writes, scheduler changes, external-system writes, or Option C automation. I understand a separate apply-time preflight, backup, rollback, and validators must pass before any production DB write.
