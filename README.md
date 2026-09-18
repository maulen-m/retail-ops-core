# retail-ops-core

The operational core of an autonomous retail business: inventory truth, demand
forecasting, purchase-order lifecycle, cashflow, and the validation gates that
decide whether any of it is allowed to touch production.

Built and run against a live apparel operation selling on
[Kaspi.kz](https://kaspi.kz). This is a **sanitized public synthesis** — the
engine, contracts, validators and test suite are intact; order data, customer
records, workbooks, databases, financial artifacts and credentials have been
removed from every commit.

1,239 commits, December 2025 – August 2026.

---

## Why this exists

A marketplace retail business generates several incompatible accounts of the
same reality. The API says one thing about an order; the CRM workbook says
another; the bank statement says a third; the stock count in the warehouse says
a fourth. Each is partly right. Decisions worth real money — reorder this SKU,
hold that price, defer this payment — depend on resolving them.

This repo is that resolution, made deterministic and testable.

## Architecture

```
core/                  164 modules, the reusable engine
  sales/               order ingestion, sales fact derivation, published truth views
  po/                  purchase-order lifecycle, part-grain payment tracking
  calc/          (20)  forecasting, safety stock, reorder points, size mix
  cashflow/      (10)  paid-capital lens, commitments, runway
  capital/             capital allocation and inventory valuation
  transfer_ledger/(16) stock movement ledger between locations
  ops/           (22)  daily operational routines
  integrations/  (14)  marketplace API, messaging, sheets
  validation/          invariant assertions used by the gates
  product_truth/       SKU identity resolution and article mapping
  parsers/ excel/ db/  hostile-format ingestion, schema, persistence
scripts/               717 runners — 121 validate_, 69 run_, 68 build_, 49 report_
tests/                 670 test modules
config/                declarative business rules — schedules, floors, decisions
excel_ui/              operator entry points (.command wrappers)
docs/                  architecture, contracts, runbooks
```

## The single-truth path

The design constraint is that **one chain** produces every published number, and
every step in it is asserted:

1. `fact_inventory_snapshot_size` — the message-date baseline; the latest
   snapshot on or before a row's date, never a later one.
2. PO dashboard generation computes PLAN and REAL_ARCHIVE rows from canonical
   math and database facts, with the plan schedule driven by
   `config/po_schedule.yaml`.
3. PO lifecycle is **part-grain** where a part exists — a PO that ships in three
   cargo batches is three payable events, not one.
4. Inbound payment truth comes from the PO part, not from the PO header.
5. The cashflow paid-capital view is anchored to bank cash plus *paid* inventory
   only. `PAID_TRUTH` is the default lens; the model ledger is an explicit
   diagnostic toggle, never the published number.
6. Published sales truth is exposed only through `view_sales_line_truth` and
   `view_sales_daily_truth` — nothing reads the raw tables directly.

Every one of those steps has a validator in `scripts/validate_*.py` that fails
closed.

## Design decisions worth calling out

**Validators outnumber everything else.** 121 of 717 scripts are `validate_*`.
This ratio is deliberate: in a system where a wrong number looks exactly like a
right number, the assertion *is* the product.

**Gates must assert meaning, not agreement.** A check that compares two
calculations proves only that they agree — including when both are wrong from
the same bad input. Validators here assert against external anchors: bank
statements, physical counts, marketplace API responses.

**Count distinct orders, not event rows.** The order feed emits several rows per
order across its lifecycle. Counting rows overstates sales. This is encoded, not
remembered.

**Fail closed on quarantine.** When identity resolution is ambiguous — an
article code that maps to two products, a header-only source gap — the row is
quarantined and the pipeline stops, rather than guessing.

**Owner decisions are configuration.** Price holds, clearance calls and cost
overrides live in `config/owner_decisions/` as dated JSON with provenance, so a
decision can be traced to when and why it was made.

**Pre-write checkpoint before production writes.** Any path that mutates the
database, a workbook or a scheduler creates a verified restorable checkpoint
first, prefers a dry-run, and requires an explicit apply flag.

## Running it

```bash
pip install -r requirements-ci.txt
cp .env.example .env         # DB path, workbook paths, API credentials

python3 scripts/db_doctor.py                  # start here when a number looks wrong
python3 scripts/validate_single_truth_alignment.py
python3 scripts/generate_po_dashboard_data.py --dry-run
python3 scripts/update_cashflow_dashboard.py --lens PAID_TRUTH --dry-run
```

```bash
pytest -q                     # 670 test modules
```

Every write script requires `--apply`. Without it you get a plan and a diff.

## What is not in this repo

Removed from the **full history**, not only from HEAD:

- **Order, customer and financial data** — every `.csv`, `.xlsx`, waybill PDF,
  `.db` / `.sqlite` snapshot, and the `data/`, `exports/`, `reports/`, `runs/`
  and `runtime/` trees.
- **Credentials** — every `.env`, service-account and token file.
- **Business material** — rollout evidence packs, owner financial documents,
  agent handoff state, `.claude/` working memory.

Brand, store and SKU identifiers are placeholders (`ACMEWEAR`, `LINE51`,
`LINE61`, `STORE-A`, `STORE-B`); merchant IDs are synthetic.

## License

MIT — see [LICENSE](LICENSE).
