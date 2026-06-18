# Owner Q&A Priority Overlay: MVOS 2026-05-18 Retained Blockers

Created: `2026-05-18`

This overlay records the human-owner clarifications that supersede the retained-blocker portion of the CodeCaptain `2026-05-18 09:08` answer where they conflict. It does not create production authority.

## Authority Boundary

Approved:

- read-only analysis;
- copied-temp-only proofs;
- local evidence artifacts;
- repo docs/tests/validator edits needed for approved copied-temp contract behavior.

Not approved:

- production DB writes;
- workbook writes;
- scheduler, LaunchAgent, or cron changes;
- source-pointer writes;
- Web_automation mutation;
- Kaspi/API/WebUI writes beyond read-only fetching;
- ad-platform writes;
- bid or budget changes;
- bank/cash movement;
- supplier payment;
- PO commitment;
- stock changes;
- price changes;
- owner publication or send;
- external writes;
- production apply.

## Owner Decisions

| Decision ID | Owner decision | Proof effect |
|---|---|---|
| `OWNER_QA_STOREB_LINE52_ALPIKA_PROCOMBAT_20260518` | STOREB product codes `11120372b` (`ALPIKA черный`) and `11942309b` (`PRO COMBAT черный`) are also Line52 product-group ads, same as the other STOREB blockers. | For copied-temp MVOS proof only, both codes may map to `CL_OC_MEN_LINE52_BLACK`; missing/unmapped positive spend must not be treated as zero spend. |
| `OWNER_QA_NIKE_SHIRT_S_ORDERABLE_20260518` | Size `S` is orderable for `CL_NEW-CLO_MEN_NIKE-SHIRT_BLACK`. | The PO dashboard proof must include `S` in size-level demand/orderability unless a later source-backed rule changes both size-level and SKU-level demand consistently. |
| `OWNER_QA_STATUS_LEDGER_SCOPED_THREE_STORE_ENOUGH_20260518` | Scoped `STOREB`/`ACMEWEAR`/`UNIVERSAL` status ledger is officially enough for the current copied-temp MVOS proof. | The board may treat scoped three-store status ledger as accepted if `11KZ` and `MELVIS` are explicitly disclosed as omitted; no full five-store green may be claimed. |
| `OWNER_QA_C3_BRIDGE_ACCEPTED_PACKETS_ONLY_20260518` | Bridge only already accepted packets/contracts. | C3 bridge proof must materialize only accepted packet rows and keep unaccepted source truth visible as blockers. |

## Owner Answers Recorded 2026-05-18T18:27:14+05:00

These answers were provided by the human owner in the orchestrator chat after the Agent 2-6 stopline review. They are canonical owner truth for future copied-temp/read-only MVOS proof lanes and should not be re-asked unless the owner later changes the answer, a proof lane requests production authority, or a source-backed contradiction appears.

| Question ID | Owner-approved answer | Proof effect | Re-ask rule |
|---|---|---|---|
| `OWNER_QA_BOUNDARY_FREEZE_APPROVED_20260518T182714_ALMT` | Owner approved freezing the business automations/workbook-editing proof window for MVOS re-baseline work. | Agents may start a read-only/copied-temp boundary re-baseline lane after verifying the surfaces are actually quiet. This is approval to freeze/re-baseline, not evidence that the freeze has already happened. | Do not re-ask permission to freeze for this repair wave; still verify the live surface is quiet before relying on the boundary. |
| `OWNER_QA_11KZ_MELVIS_INACTIVE_20260518T182714_ALMT` | `11KZ` and `MELVIS` are currently fully inactive stores. Only the human owner can activate them again in the future by declaring them active. | Current MVOS proof may use `MVOS_SCOPE_ACTIVE_BUSINESS_THREE_STORE` for `STOREB`, `ACMEWEAR`, and `UNIVERSAL`, with explicit no-full-five-store-green disclosure. | Do not re-ask why `11KZ`/`MELVIS` are excluded unless the owner declares either store active again. |
| `OWNER_QA_NO_NEW_PAYMENT_BRIDGE_20260518T182714_ALMT` | There is no new May 18 payment evidence. Owner approves a May 18 no-new-payment bridge for copied-temp proof only. | `src_payment_evidence_root` may use a May 18 copied-temp no-new-payment contract. No cash movement, supplier payment, production write, or owner publication is authorized. | Do not re-ask for May 18 payment evidence in this proof wave unless new payment evidence appears. |
| `OWNER_QA_CASH_BALANCES_RESERVE_20260518T182714_ALMT` | Use the latest `Cash_Balances` source. The `1,500,000 KZT` reserve is a separate non-spendable buffer. | `src_bank_manual_ingest` may use the latest `Cash_Balances` route for copied-temp proof, with the reserve visible but excluded from spendable operating cash. | Do not re-ask whether the reserve is spendable; it is non-spendable unless owner later changes that explicitly. |
| `OWNER_QA_STOREB_LINE52_TWO_CODES_20260518T182714_ALMT` | Owner approves copied-temp mapping of `11120372b` and `11942309b` to `CL_OC_MEN_LINE52_BLACK`. | The `19,104.96 KZT` positive spend attached to those two codes may be mapped to Line52 in copied-temp ads/profit proof. Missing spend must still never be zeroed. | Do not re-ask this mapping unless moving from copied-temp proof into production authority or source evidence contradicts it. |
| `OWNER_QA_PO4_LINE61_SHORTAGE_20260518T182714_ALMT` | PO-4.0 Line61 actual received is `92`; ordered/cargo was `115`; shortage `23` is real. | PO/inbound proof must treat the 23-unit delta as a real shortage, not as missing received stock. Known shortages: XL `7`, 2XL `5`, 3XL `6`, 4XL `5`. | Do not re-ask whether the 23-unit shortage is real; only ask if a later source changes received/ordered facts. |
| `OWNER_QA_HIGH_STOCK_EXCEPTIONS_RETAINED_20260518T182714_ALMT` | Keep all `9` high-stock exceptions visible as retained blockers. | Exception-queue proof may keep those rows as explicit retained blockers; they must not be hidden or silently converted to green. | Do not re-ask whether to hide or clear the 9 blockers without warehouse/source proof or new owner instruction. |

## Owner Answers Recorded 2026-05-18T22:02:03+05:00

These answers were provided after Agent910 narrowed the MVOS copied-temp proof to five retained blocker classes. They are canonical owner truth for the next retained-blocker repair wave.

| Question ID | Owner-approved answer | Proof effect | Re-ask rule |
|---|---|---|---|
| `OWNER_QA_STOREB_HEADER_ONLY_WEBUI_API_FETCH_20260518T220203_ALMT` | Use Computer Use / Chrome / read-only WebUI archive download or fetch, with API fallback, to search the 15 STOREB header-only orders. If the orders still remain header-only after read-only fetch, keep them quarantined. | A bounded execution agent may use browser or API read-only evidence acquisition for the 15 STOREB order IDs only. It may create local evidence and either recover identity-bearing product lines on a copied DB or keep the rows as explicit retained quarantines. | Do not re-ask whether to use read-only WebUI/API fallback for these 15 rows in this wave. Re-ask before any WebUI mutation, external write, production DB write, or workbook write. |
| `OWNER_QA_NO_FRESHER_STOCK_SOURCE_20260518T220203_ALMT` | No fresher stock source than the already-available evidence exists yet. | Stock freshness must not be faked. The next wave may document this as an honest retained blocker, identify the exact source required for green, and run copied-temp proofs without claiming source-backed May 18 stock truth. | Do not ask the owner for a fresher stock source again in this wave unless a new source file/export is created. |
| `OWNER_QA_PO4_LINE61_SHORTAGE_RECONFIRMED_20260518T220203_ALMT` | PO-4.0 Line61 ordered `115`, actual received `92`, shortage `23` is the business truth. | Validator and proof work must treat this as a real shortage, not a workbook error or missing received stock. | Do not re-ask whether the 23-unit shortage is real unless later source evidence changes ordered or received counts. |
| `OWNER_QA_INBOUND_WORKBOOK_SCHEMA_CORRECTION_20260518T220203_ALMT` | Missing `To_pay_BASE_KZT` / `To_pay_DLV_KZT` columns are not expected. The workbook/source likely changed format because of recent owner edits; overall workbook architecture remains canonical priority and the validator/source route should inspect the migrated cells/columns rather than downgrade the workbook. | A serialized code/test lane may inspect the workbook read-only, update docs/tests/validator logic if the columns moved or have equivalent canonical labels, and produce copied-temp proof. It may not edit the workbook. | Re-ask only if multiple conflicting migrated column candidates exist or if correcting the validator would change business formulas instead of schema-location parsing. |

## Required Labels

Status-ledger proof label:

```text
SCOPED_STATUS_LEDGER_STOREB_ACMEWEAR_UNIVERSAL_ONLY_11KZ_AND_MELVIS_OMITTED_AND_DISCLOSED_NO_FULL_FIVE_STORE_STATUS_LEDGER_GREEN
```

C3 bridge label:

```text
COPIED_TEMP_SOURCE_FRESHNESS_BRIDGE_ACCEPTED_PACKETS_ONLY_NO_PRODUCTION_AUTHORITY
```

STOREB mapping label:

```text
OWNER_CONFIRMED_9_STOREB_BLOCKED_PRODUCT_CODES_ARE_LINE52_PRODUCT_GROUPS_2026-05-18
```

## Stoplines

- Do not treat missing STOREB spend as zero spend.
- Do not use this overlay for production `db/app.db` apply.
- Do not use scoped status-ledger proof to claim full five-store status-ledger green.
- Do not bridge unaccepted C3 source packets.
- Do not commit PO or stock changes from the Nike-shirt S clarification.
- Do not treat the owner-approved freeze answer as proof that the DB/workbook boundary is currently frozen; verify quiet state first.
- Do not count the `1,500,000 KZT` reserve as spendable operating cash.
- Do not treat the May 18 no-new-payment bridge as cash movement, payment authority, production authority, or owner-publication authority.
- Do not convert the 9 high-stock retained blockers into hidden green output.
- Do not treat absence of a fresher stock source as green stock freshness.
- Do not insert the 15 STOREB header-only rows into product truth unless read-only WebUI/API/local evidence produces identity-bearing product lines.
- Do not edit the inbound workbook while repairing migrated workbook-schema parsing.
