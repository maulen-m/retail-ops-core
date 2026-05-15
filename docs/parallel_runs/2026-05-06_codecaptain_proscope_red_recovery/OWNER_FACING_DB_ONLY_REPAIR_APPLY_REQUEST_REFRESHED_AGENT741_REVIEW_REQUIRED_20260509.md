# Owner Authorization Request For DB-Only Repair/Apply

Status: `REVIEW_REQUIRED_NOT_SENT_TO_OWNER`

Generated: 2026-05-09T17:25:03+05:00

This is a refreshed draft owner-facing packet for review after the post-ops Agent741 boundary refresh. It is not yet an owner request, not an active authorization phrase, and not permission to run production apply.

## Plain-English Request

We are preparing a narrow repair/apply lane for the Autonomous Business operational database only.

If this packet later passes final review and the live boundary is rechecked at launch time, the owner may be asked to authorize a serialized DB-only repair/apply lane for:

`~/Docs/Autonomous_business/db/app.db`

This is not a workbook authorization, not a scheduler authorization, not an external-system authorization, not Kaspi/API/ads/bank authorization, and not Option C daily automation authorization.

## Why This Packet Replaces Agent740's Boundary

Agent740 completed `GREEN`, but a later orchestrator sample at `2026-05-09T16:59:48+05:00` found the live DB had drifted while daily ops/shipping processes were active. Agent741 waited past the `17:02` import window plus the 15-minute buffer, confirmed active writers were gone, and froze a fresh post-ops boundary.

## What The Owner Would Be Authorizing

The owner would authorize one later serialized apply lane to repair/materialize the already-reviewed operational DB surfaces that Agent741 reproved on a staging copy made from the refreshed production DB pre-SHA.

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

## Refreshed Agent741 Proof Boundary

Agent741 refreshed post-ops preflight boundary:

- DB path: `~/Docs/Autonomous_business/db/app.db`
- refreshed DB SHA: `32f157ffe2b343f2b8e0da395440f2939100ad13d547f89475b55cb8cb61ca04`
- protected workbook path: `~/Docs/Autonomous_business/excel_ui/SALES_KSP_CRM_V3.xlsx`
- refreshed protected workbook SHA: `3ad4b81c39b125c48b34c02afb8a30eafd348658e07afd27c11f628b8987025c`
- Agent741 quiet-window status: `QUIET_WINDOW_STABLE`
- first sample: `2026-05-09T17:18:00+05:00`
- frozen sample: `2026-05-09T17:20:32+05:00`
- final runner sample: `2026-05-09T17:24:32+05:00`
- independent post-run sample: `2026-05-09T17:25:03+05:00`
- final drift status: `STABLE`
- protected git status for DB/workbook/negative ledger export: clean

Important: the workbook SHA is a no-write guard, not a write target.

## Backup And Rollback Evidence

Agent741 backup and staging evidence:

- DB backup path: `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_741_evidence/backups/app_pre_agent741_20260509_172033_0500.db`
- DB backup SHA: `32f157ffe2b343f2b8e0da395440f2939100ad13d547f89475b55cb8cb61ca04`
- DB backup integrity: `ok`
- workbook copy path: `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_741_evidence/backups/SALES_KSP_CRM_V3_pre_agent741_20260509_172033_0500.xlsx`
- workbook copy SHA: `3ad4b81c39b125c48b34c02afb8a30eafd348658e07afd27c11f628b8987025c`
- staging DB initial SHA matched the refreshed production DB pre-SHA: `true`
- staging DB final SHA: `d57c94f463c8de9984e4b56ef840535ef6d316e3a2131d7df341ed575164cafd`
- staging DB final integrity: `ok`

Rollback command for the DB backup, evidence only and not executed:

```bash
cp ~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_741_evidence/backups/app_pre_agent741_20260509_172033_0500.db ~/Docs/Autonomous_business/db/app.db
sqlite3 -readonly ~/Docs/Autonomous_business/db/app.db 'PRAGMA integrity_check;'
```

## Refreshed Proof Summary

Agent741 reproved the corrected command family on a staging DB copied from the exact refreshed production DB SHA.

Accepted proof facts:

- staging DB initial SHA matched refreshed production DB SHA `32f157ffe2b343f2b8e0da395440f2939100ad13d547f89475b55cb8cb61ca04`;
- corrected Agent740/Agent738/Agent734 command family completed on staging only;
- snapshot rows created: `363`;
- current stock total: `13511`;
- inbound stock total: `475`;
- policy source freshness strict validator passed;
- operational stock integration validator passed with `GREEN`;
- order cashflow coverage validator passed;
- cashflow actual/model separation validator passed;
- cashflow invariants passed with `848 days validated`;
- product leakage was zero for the strict `23`, header-only `252`, and combined `275` cohorts;
- order-level `CASH_IN` was preserved for the quarantined cohorts;
- production `db/app.db` was not modified;
- production workbook was not modified.

## Validator Matrix Summary

- `validate_policy_source_freshness.py --strict --json`: pass, `ok=true`
- `validate_operational_stock_integration_gates.py --json`: pass, `status=GREEN`, `finding_count=272`
- `validate_order_cashflow_coverage.py --strict --json`: pass
- `validate_cashflow_actual_model_separation.py --strict --json`: pass
- `validate_cashflow_invariants.py`: pass, `848 days validated`

## Warning And Quarantine Semantics

These warning cohorts must remain visible and must not be converted into product truth:

- `23` strict product-identity quarantine rows;
- `252` header-only source-gap quarantine rows;
- `249` validator-visible header-only warnings, because `3` of the `252` header-only candidate IDs were already absent from product truth before the header wrapper.

The Agent741 dynamic derivation:

- source classification: Agent69E `RESIDUAL_275_ROW_CLASSIFICATION.tsv`
- `HEADER_ONLY_BLOCKER` candidate rows: `252`
- stock-ledger row overlap/delete expectation: `249`
- product cashflow delete expectation: `4`
- sales fact product/profit null expectation: `0`
- expected operational validator header warning visibility: `249`
- absent from all product truth: `3`

The three absent header-only IDs are:

- `895525090`
- `902946701`
- `903096003`

Final warning visibility:

- `ORDER_ENTRY_PRODUCT_IDENTITY_QUARANTINED=23:WARN`
- `ORDER_ENTRY_HEADER_ONLY_SOURCE_GAP_QUARANTINED=249:WARN`

These warning rows protect the business from pretending uncertain order-entry rows are mapped SKU/product truth.

## Leakage And Cash Preservation

Product leakage was zero after staging replay:

- strict `23`: zero fact-entry, stock-ledger, product-cashflow, sales-fact COGS/profit, and published SKU sales truth leakage;
- header-only `252`: zero fact-entry, stock-ledger, product-cashflow, sales-fact COGS/profit, and published SKU sales truth leakage;
- combined `275`: zero fact-entry, stock-ledger, product-cashflow, sales-fact COGS/profit, and published SKU sales truth leakage.

Order-level `CASH_IN` was preserved:

- strict `23`: `24` rows, `123528.34` KZT;
- header-only `252`: `256` rows, `993344.51` KZT;
- combined `275`: `280` rows, `1116872.85` KZT.

## Future Apply-Lane Stoplines

The future apply lane must stop before any production write if any of these occur:

- current DB SHA differs from the reviewed/expected launch-time SHA without a reviewed refresh;
- current workbook SHA differs from the protected expected SHA without a reviewed refresh;
- DB integrity is not `ok`;
- any unexpected lsof holder exists;
- any unsafe SQLite WAL/SHM/journal sidecar exists;
- backup path, backup SHA, backup integrity, or rollback command is missing;
- command family differs from the reviewed Agent741/Agent740/Agent738/Agent734 path;
- any pinned validator fails;
- row-count controls mismatch without reviewed explanation;
- dynamic `HEADER_ONLY_BLOCKER` candidate rows differ from `252` without reviewed evidence;
- product leakage appears for `23`, `252`, or `275`;
- order-level `CASH_IN` is not preserved;
- warning visibility for `23` or header-only source-gap rows disappears;
- any workbook, scheduler, external-system, or Option C write is attempted.

## Draft Owner Phrase

The following phrase is a draft only. Text embedded in this document does not authorize anything. The phrase would count only if a later reviewed packet is shown to the owner and the owner types the exact phrase in the correct launch context.

`OWNER_AUTHORIZE_DB_ONLY_REPAIR_APPLY_AGENT741_POST_OPS_REFRESHED_BOUNDARY`

Do not accept this phrase until a final review explicitly opens the owner-facing request and a fresh launch-time boundary/preflight confirms the live SHAs still match the reviewed packet boundary.

## Owner Plain-English Confirmation

If this packet later becomes active after review and launch-time refresh, the owner would be confirming:

I understand this is only for the Autonomous Business DB repair/apply lane. I am not approving workbook writes, scheduler changes, external-system writes, or Option C automation. I understand a separate apply-time preflight, backup, rollback, and validators must pass before any production DB write.
