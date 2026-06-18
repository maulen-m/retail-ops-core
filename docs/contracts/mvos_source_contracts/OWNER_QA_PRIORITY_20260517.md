# Owner Q&A Priority Overlay: MVOS 2026-05-17

Created: `2026-05-17`

This overlay records owner decisions that are authoritative above the CodeCaptain `2026-05-17 22:06` answer where they conflict, while preserving all repo safety boundaries.

## Authority Boundary

Approved:

- read-only source fetching;
- copied-temp-only proof work;
- repo docs/tests/validator edits needed for approved contract behavior;
- local evidence artifacts;
- Chrome Auto Connect or headless Playwright fallback for read-only fetching if existing API routes fail.

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
| `OWNER_QA_STOREB_MARKETING_UNIVERSAL_SWITCHER_20260517` | STOREB Kaspi Marketing should be fetched through `UNIVERSAL` login/switcher. | Ads source refresh should use `UNIVERSAL_SWITCHER_FOR_STOREB` as the read-only route for STOREB. |
| `OWNER_QA_META_FETCH_MAY13_17_20260517` | Meta/Facebook May 13-17 evidence should be fetched, not scoped out by default. | Meta out-of-scope remains fallback only, not the primary route. |
| `OWNER_QA_API_CANCELLING_EXPOSURE_20260517` | The five `KASPI_DELIVERY / CANCELLING` lifecycle rows may be treated as copied-temp non-delivered exposure. | Use `API_CANCELLING_NON_DELIVERED_EXPOSURE_FOR_COPIED_TEMP_ONLY_NO_WEBUI_STATUS_CHANGE_AT`; do not create WebUI `status_change_at`. |
| `OWNER_QA_DAY_COMPLETE_CANCELLED_RETURNED_EXCLUSION_20260517` | `CANCELLED/ARCHIVE` and `RETURNED/ARCHIVE` rows may be excluded from size-complete requirements. | Day-complete validator-contract lane may implement this as copied-temp/code-contract behavior. |
| `OWNER_QA_DAY_COMPLETE_MISSING_LINE_ITEM_EXCEPTION_20260517` | Blank SKU / `nan` offer rows may be treated as missing-line-item exceptions, not employee size-entry failures. | Day-complete validator-contract lane may classify these separately from true size-entry incompleteness. |
| `OWNER_QA_DAY_COMPLETE_861147900_MANUAL_TEXT_20260517` | Order `861147900` may be manually classified from offer text `Комплект Antec RASH-921 Рашгард 5 в 1 черный 46, 48`. | Do not leave this row as generic unknown when applying the owner-approved day-complete contract. |

## Stoplines

- Missing ads spend must not become zero spend.
- API lifecycle evidence must not populate WebUI `status_change_at`.
- Parent-unit COGS must not be called ChildSum component economics.
- Copied-temp proof must not become production truth.
- A retained-blocker board proof must not be labeled GREEN.

