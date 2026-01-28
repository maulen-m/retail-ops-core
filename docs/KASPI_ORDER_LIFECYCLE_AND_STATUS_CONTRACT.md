# Kaspi Order Lifecycle and Status Contract (Seller Cabinet ↔ API ↔ Internal Stages)

Version: 2026-01-28  
Purpose: Single, unambiguous “truth contract” for how Kaspi orders progress through lifecycle stages, and how we map Seller Cabinet semantics to Kaspi API fields and our internal stage codes.

## Sources of truth

1) Official Seller lifecycle (RU, immutable):  
   `docs/api_docs/official/kaspi_order_lifecycle_ru.md`  
   - New order SLA: must process within 3 working hours (Express: 60 minutes), else auto-cancel “out of stock”.  
   - Preorder rules: “В пути” stage, preorder max 30 days, “Прибыл” action.  
   - Delivery issuance: after code entry, status becomes “Выдан” and moves to Archive.  
   - Pickup: buyer must pick up within 3 working days, else auto-cancel.  
   - Returns: customer can request return within 14 days; seller decision SLAs apply.  
   (All of the above are defined in the official RU doc.)

2) Official Kaspi API semantics:  
   - API `state` values: NEW, SIGN_REQUIRED, PICKUP, DELIVERY, KASPI_DELIVERY, ARCHIVE  
   - API `status` values: APPROVED_BY_BANK, ACCEPTED_BY_MERCHANT, COMPLETED, CANCELLED, CANCELLING, KASPI_DELIVERY_RETURN_REQUESTED, RETURNED  
   (See `docs/api_docs/kaspi_api_orders_QA_official.md` and `docs/api_docs/Kaspi_API_Official_document_8.12.2025_GP.md`.)

## Non-negotiable definitions

### 1) API state vs API status (do not mix)
- `state` = broad bucket (NEW / KASPI_DELIVERY / PICKUP / ARCHIVE, etc.)
- `status` = processing milestone (APPROVED_BY_BANK → ACCEPTED_BY_MERCHANT → COMPLETED, etc.)
- Some Seller Cabinet “stages” are **sub-stages** that do NOT correspond to a unique API `status` value; they are represented by a combination of:
  - state + status + flags (assembled, preOrder, signatureRequired, returnedToWarehouse, etc.) + dates.

### 2) Internal StageCode is our stable contract
We use StageCode to unify logic across:
- order sync selection
- waybill selection
- cashflow event translation
- alerts & SOP checks

StageCode must be computed from the API payload deterministically.

Recommended StageCodes (minimum set):
- SIGN_REQUIRED
- NEW_APPROVED
- PREORDER_IN_TRANSIT
- ACCEPTED_PENDING_ASSEMBLY
- ASSEMBLED_PENDING_HANDOVER
- IN_DELIVERY
- ISSUED_COMPLETED
- CANCELLING
- CANCELLED
- RETURN_REQUESTED
- RETURNED

## Seller Cabinet lifecycle summary (operational)

### A) New orders
- Seller Cabinet tab: “Новые”
- Seller Cabinet status: “Новый”
- SLA: process within 3 working hours; Express delivery within 60 minutes; otherwise auto-cancel as “out of stock”.  
- API mapping:
  - state=NEW
  - status=APPROVED_BY_BANK
  - signatureRequired=false (we exclude signature-required from automation)
- Internal StageCode: NEW_APPROVED

### B) Preorder orders
- Seller Cabinet subtab: “Предзаказ”
- Seller Cabinet status: “В пути”
- Preorder term: max 30 calendar days.
- When item arrives: action “Прибыл” changes the order to “Принят партнером”.
- API mapping:
  - preOrder=true
  - status usually ACCEPTED_BY_MERCHANT (and then ARRIVED may exist as a status-change action in API for preorders)
- Internal StageCode: PREORDER_IN_TRANSIT (until ARRIVED confirmed)

### C) Accepted → Packing → Handover (Kaspi Delivery)
- After acceptance, orders flow through:
  - “Упаковка” (packing / assemble preparation)
  - “Передача” (handover to acceptance point / courier planning)
- Internal StageCodes:
  - ACCEPTED_PENDING_ASSEMBLY
  - ASSEMBLED_PENDING_HANDOVER

### D) Delivery → Issued (delivered)
- When buyer receives the order, status becomes “Выдан” and the order moves to “Архив”.
- API mapping:
  - status=COMPLETED (expected)
  - state moves toward ARCHIVE
- Internal StageCode: ISSUED_COMPLETED

### E) Cancelled during delivery
- Seller Cabinet:
  - “Отменены при доставке” status “Ожидает отмены”
  - later “Возвращены на склад”
  - must pick up returned goods within 30 days or it is disposed
  - then status “Отменен” and moves to archive
- API mapping:
  - status=CANCELLING (expected while “Ожидает отмены”)
  - status=CANCELLED (expected once cancelled)
  - returnedToWarehouse flag may appear
- Internal StageCodes:
  - CANCELLING → CANCELLED

### F) Pickup (самовывоз)
- Buyer must pick up within 3 working days or the order is auto-cancelled.
- API mapping:
  - state=PICKUP
- Internal StageCode:
  - depends on status (APPROVED / ACCEPTED / COMPLETED / CANCELLED)

## Returns (cashflow-critical)

- Customer can request return within 14 calendar days after receiving the goods (goods of proper quality).  
- Return requests appear in “Возвраты”, and if the seller does not act by the end of the review period the request can be considered accepted (per official process).
- Internal StageCodes:
  - RETURN_REQUESTED (status=KASPI_DELIVERY_RETURN_REQUESTED)
  - RETURNED (status=RETURNED)

Cashflow implication:
- Refund reserve should treat orders within the return window as exposure until the window ends (conservative scenario).
- Delivery cost is treated as an operating cost (not negative COGS) per your contract.

## Implementation contract (for engineers/agents)

When editing ANY Kaspi order logic:
1) Update `core/integrations/kaspi_order_stage.py` (single source of truth).
2) Update tests first:
   - `tests/test_kaspi_order_stage.py`
3) Only then update:
   - order sync selection
   - waybill selection
   - cashflow translator triggers
4) Gates must be green:
   - `pytest -q`
   - `scripts/lint_docs.sh`

5) Engineering Rules (non-negotiable)

Do not compare raw strings state == ... or status == ... outside the StageCode classifier module.

Any new pipeline logic must add/extend StageCode tests first.

Docs must not duplicate lifecycle mapping tables elsewhere (link here instead).