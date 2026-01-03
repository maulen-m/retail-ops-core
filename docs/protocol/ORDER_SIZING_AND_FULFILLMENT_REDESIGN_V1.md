# ORDER_SIZING_AND_FULFILLMENT_REDESIGN_V1

Problem statement

Manual sizing is currently a human-in-the-loop choke point:

A customer’s size choice changes the SKU (clothes), so shipping cannot proceed without size resolution.

WhatsApp restrictions removed the previous automation, forcing manual extraction and entry into Excel.

Excel files have been “lost” twice — which is a giant reliability red flag for an operational system.

Why the current workflow is not efficient

Manual copy/paste pipeline
Human reads WhatsApp → retypes into Excel → derives MY_SIZE → triggers shipping. That scales linearly with orders and creates fatigue errors.

Excel as implicit system-of-record
When sizes live “only in a workbook,” you have:

no audit trail,

no idempotency,

no atomicity,

no safe re-run behavior.

Fragile file logistics = operational downtime
When key XLSX files go missing, the entire day’s pipeline can be blocked. The sizing protocol explicitly calls out that these files “will always get lost again” if stored inside the repo tree instead of a proper data directory + backups + preflight restore.

Target state (design)

DB is the system-of-record; Excel is optional UI.

Orders live in fact_orders_kaspi

Customer measurements live in fact_order_measurements

Size decisions live in fact_order_size_decisions

Shipping/waybill code reads only from DB

Excel may still exist as a UI surface during transition, but never blocks ops

Migration plan + deadlines (hard commitments)

Phase 0 — Stabilize + stop losing files (deadline: 2026‑01‑04)
Deliverables:

DATA_DIR standard (external to repo), preflight, backups, no hardcoded workbook names.

waybill_grouping

Phase 1 — DB-first manual sizing queue (deadline: 2026‑01‑07)
Deliverables:

“Sizing queue” CLI or local web UI for entering height/weight or choosing size.

Size engine suggestions + operator confirmation.

Audit trail (who/when/source/confidence).

Phase 2 — Reduce manual work with automation (deadline: 2026‑01‑12)
Deliverables:

Measurement ingestion path (WhatsApp API once verified, or web form).

Auto size assignment for high-confidence cases.

Human handles exceptions only.

Definition of done (ROI)

Shipping pipeline runs daily without workbook hard-fails.

Size decisions are never “only in Excel.”

Manual work per order drops materially (target: majority of orders auto-suggested; humans only confirm).
