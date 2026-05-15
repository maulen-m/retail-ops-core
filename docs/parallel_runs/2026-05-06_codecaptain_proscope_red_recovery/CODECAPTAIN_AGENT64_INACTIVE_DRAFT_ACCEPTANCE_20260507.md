# CodeCaptain Agent64 Inactive Draft Acceptance - 2026-05-07

Decision timestamp: `2026-05-07 13:56:00`

## Source

Highest-authority CodeCaptain answer:

`~/Docs/Oracle/Autonomous_business/2026-05-07/131850_TASK-000_codecaptain-agent64-inactive-owner-phrase-review/Answer/Code_Captain_2026-05-07_13_56_00.md`

Review pack:

`~/Docs/Oracle/Autonomous_business/2026-05-07/131850_TASK-000_codecaptain-agent64-inactive-owner-phrase-review/`

## Decision

CodeCaptain decision:

`ACCEPT_INACTIVE_DRAFT_FOR_LATER_OWNER_REQUEST`

This accepts Agent64's inactive owner phrase draft as the basis for a later owner-request lane.

This does not authorize:

- production apply today;
- asking the owner for the phrase today;
- treating the phrase as active;
- reusing or reviving the old Agent54 owner phrase;
- workbook mutation;
- scheduler mutation;
- external API, web UI, browser automation, bank, Kaspi, ads platform, Google, or Web_automation writes;
- Option C production promotion.

## Accepted Evidence Chain

- Agent64 inactive phrase draft is accepted as an inactive basis only.
- Agent62 remains the proof authority for the pinned `2026-05-04` temp-only surface.
- Agent63 YELLOW items remain visible and must not be converted to GREEN.
- The old Agent54 contract remains historical and blocked for this path.

## No Fixes Required To Agent64 Draft

CodeCaptain required no patch to the inactive Agent64 draft itself.

Future requirements are later-lane preconditions, not edits to Agent64:

- fresh apply-time production DB SHA;
- fresh workbook SHA;
- DB integrity proof;
- SQLite sidecar and `lsof` safety proof;
- timestamped backup path, backup SHA, and backup integrity;
- rollback command;
- exact command family;
- env gate plus `--apply`;
- pinned validator replay;
- row-count proof;
- leakage proof;
- explicit owner-facing YELLOW limitations.

## Stoplines For Next Lane

The next lane must stop as `RED` if:

- Agent64's inactive draft is treated as active authorization;
- the owner is asked before fresh apply-time boundary and active-request review exist;
- old Agent54 phrase is reused, quoted as active, or treated as a valid substitute;
- production DB, workbook, scheduler, Web_automation, APIs, browser automation, banks, Kaspi, ads platforms, Google, or external systems are mutated from this packet;
- current production hashes are treated as proof authority rather than fresh boundary evidence;
- production DB or workbook SHA differs from the new readiness contract;
- `PRAGMA integrity_check` is not `ok`;
- any SQLite WAL/SHM/journal sidecar or active `lsof` holder makes replacement unsafe;
- backup path, backup SHA, backup integrity, or rollback command is missing;
- pinned validators are not rerun with the `2026-05-04` boundary or reviewed equivalent;
- unpinned/no-as-of validators are used as readiness proof for this pinned contract;
- row-count matrix or leakage matrix differs without reviewed explanation;
- post-as-of rows appear in `order_status_event`, `sales_fact_v2`, `stock_ledger`, `fact_cashflow_events`, or `fact_cashflow_daily`;
- the `23` STOREB quarantine semantics are lost or leak into product-level publication;
- workbook tail rows `8053-8137` are allowed to feed another send build before canonical status refresh;
- `912168984` is shipped or repaired without bounded current-status check and manual size confirmation;
- Option C moves beyond validate-only before a production release anchor exists;
- ad hoc SQL or broad repo refactors are introduced into the apply lane.

## Next Safe Action

Open the next lane as an owner-request preflight/activation lane, not an apply lane.

That lane should take the accepted inactive Agent64 draft, perform fresh apply-time boundary checks against the then-current production DB and workbook, generate backup/rollback/preflight evidence, and produce an active owner-request packet for review.

Do not ask the owner until that lane passes and the active request wording is reviewed.
