# Cross-Repo Business Event Bridge V1

Status: review-only prototype contract
Owner approval scope: read-only source inspection, local evidence packets, and review inbox generation only

## Purpose

The bridge is the durable way for Autonomous_business to ingest business-relevant facts from sibling repos without manual copy-paste and without silently mutating production truth.

V1 converts selected local evidence from:

- `~/Docs/Autonomous_business`
- `~/Cowork/Projects/Sourcing-Research`
- `~/Cowork/Projects/E-commerce`

into normalized, append-only business event packets under an Autonomous_business review inbox. These events are evidence candidates, not production DB rows, not workbook edits, and not source-pointer changes.

## Non-Authority Boundary

V1 does not authorize:

- production DB writes
- workbook writes
- source-pointer writes
- scheduler or LaunchAgent changes
- Web_automation writes
- Kaspi/API/WebUI writes
- external messages or supplier messages
- payment, PO commitment, stock change, price change, or ads change
- owner publication
- production preflight or production apply

Any downstream production use needs a separate exact owner approval phrase and the repo write-gated path.

## Source Priority

The bridge does not decide business truth by itself. It preserves source provenance so the human owner, CodeCaptain, or a later write-gated lane can decide.

V1 source tiers:

1. Owner-approved Autonomous_business review packet fields and sidecars.
2. Sourcing-Research event summaries, payment proofs, packing-list events, and operator workbench files.
3. E-commerce PO amendment markdown and machine-readable amendment JSON.
4. Derived Autonomous_business review outputs from copied-temp or review-only lanes.

If source files conflict, emit separate events and mark the event `gate=YELLOW` instead of overwriting or merging away the conflict.

## Event Schema

Every event packet row uses these fields:

| Field | Meaning |
| --- | --- |
| `event_id` | Deterministic hash ID for the normalized event. |
| `event_schema_version` | Contract version, currently `cross_repo_business_event_v1`. |
| `bridge_run_id` | Timestamped run folder ID. |
| `created_at` | Local creation timestamp of the bridge output. |
| `event_type` | Normalized business event type. |
| `event_time` | Business event time from source evidence, if known. |
| `event_time_basis` | Why that event time is valid or limited. |
| `source_repo` | `Autonomous_business`, `Sourcing-Research`, `E-commerce`, or `UNKNOWN`. |
| `source_path` | Absolute source path used for this normalized row. |
| `source_sha256` | Current SHA-256 hash for the source file. |
| `source_exists` | Whether the source file exists at generation time. |
| `source_ref` | Route label, line item, or source anchor inside the file. |
| `po_id` | PO route identifier when known. |
| `po_line_id` | Line-level ID when known. |
| `product_family` | Product or family label such as `LINE31`. |
| `sku_key` | Candidate canonical SKU key. |
| `sku_id` | Candidate SKU ID, if available. |
| `size` | Size, if row-level. |
| `color` | Color or source-set descriptor. |
| `quantity` | Unit quantity, as a string for CSV/JSON stability. |
| `unit` | Unit label such as `sets`, `units`, or `CNY`. |
| `amount` | Monetary amount, if the event is financial. |
| `currency` | Currency code such as `CNY`, `USD`, or `KZT`. |
| `amount_kzt` | KZT value when source-backed or clearly labeled as estimate. |
| `fx_basis` | FX basis or why no KZT conversion is applied. |
| `counterparty` | Supplier, cargo, platform, or merchant counterparty when known. |
| `location` | Relevant business location. |
| `status` | Source status or normalized state. |
| `inventory_treatment` | How inventory views should treat this event. |
| `cash_treatment` | How cash/payables views should treat this event. |
| `confidence` | `HIGH`, `MEDIUM`, `LOW`, or source-provided value. |
| `gate` | `GREEN`, `YELLOW`, or `RED` for the event-level review status. |
| `requires_owner_action` | `true` when the event needs owner mapping, acceptance, or missing proof. |
| `notes` | Human-readable summary. |
| `raw_payload` | JSON string containing source row details that should not be flattened away. |

## Seed V1 Event Types

The first bridge seed is the LINE31/LINE31S inbound and packaging case from the V4 inventory-capital proposal.

Supported seed events:

- `PO_INBOUND_ASTANA_CANDIDATE`
- `PO_IN_TRANSIT_YIWU_RECEIPT_CANDIDATE`
- `SUPPLIER_PREPAYMENT_ACKED`
- `PACKAGING_MATERIAL_ALLOCATION_CONFIRMED`
- `PACKAGING_MATERIAL_ALLOCATION_PENDING_CONFIRMATION`
- `PACKAGING_MATERIAL_SUBTOTAL_WORKING`
- `PACKAGING_ADVANCE_CREDIT_WORKING`
- `PACKAGING_ADVANCE_UNALLOCATED_STRICT`
- `PACKAGING_LABOR_RESERVE_WORKING`
- `PACKAGING_AND_LABOR_RESERVE_WORKING`
- `WORKING_PO_TOTAL_ESTIMATE`
- `WORKING_BALANCE_DUE_ESTIMATE`
- `PO1O_SUPPLIER_BASE_PAYMENT_ACKED`
- `PO1O_FREIGHT_PAYABLE_OPEN`
- `OWNER_REPORTED_TIMING_RULE_PENDING_EVIDENCE`
- `SOURCE_MAPPING_QUARANTINE`

## Review Inbox Contract

Each run creates a timestamped folder:

```text
exports/validation/cross_repo_business_event_bridge_v1_<run_id>/
```

Required files:

- `business_events.jsonl`
- `business_events.csv`
- `event_bridge_manifest.json`
- `source_files_manifest.csv`
- `review_inbox.md`
- `closeout.md`

The inbox is review-only. A later lane may read it, but no validator may treat it as applied production truth unless a separate write-gated approval explicitly authorizes that apply.

## CLI

Command:

```bash
python3 scripts/build_cross_repo_business_event_bridge_v1.py \
  --v4-root exports/validation/inventory_capital_po_decision_v4_line31_inbound_integration_proposal_20260527_204954
```

Useful flags:

- `--output-root PATH`: default `exports/validation`.
- `--run-id TEXT`: deterministic run folder suffix for tests or handoffs.
- `--strict`: fail non-zero when a source file is missing or its hash differs from the upstream manifest.
- `--json`: print machine-readable run summary to stdout.

The command is read-only with respect to source repos and writes only a new local review packet folder.

## Trigger Points

Use this bridge whenever a task needs Autonomous_business to consume time-sensitive business facts from Sourcing-Research or E-commerce, especially:

- supplier payment acknowledgement
- PO amendment or size split
- cargo pickup or warehouse receipt
- packing list, carton, weight, volume, or ETA evidence
- supplier quote, prepayment, or remaining payable estimate
- stock-reservation lead time or timing-risk evidence
- cross-repo facts that would otherwise be manually pasted into chat

Do not use this bridge to send supplier messages, change stock, change prices, commit a PO, or update production ledgers. It only prepares review-grade event packets.

## Gate Rules

- `GREEN`: all referenced sources exist, hashes match prior manifests when available, and all emitted events are source-backed review rows.
- `YELLOW`: the packet is usable for review, but source gaps, hash drift, mapping quarantines, owner-reported-but-unverified facts, or working estimates remain.
- `RED`: the bridge cannot safely identify its source packet, required sidecars are missing, or a protected production surface mutation is detected during a lane that claimed read-only behavior.
