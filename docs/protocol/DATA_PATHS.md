# DATA_PATHS
## Purpose

Define canonical folders for the **Autonomous_business** repo so that
Project 3 (CRM/Python), Excel UI, and future tools all speak the same language
about where data lives.

Root assumption: repo lives at  
`~/Docs/Autonomous_business/`
db/ folder contains app.db (SQLite) and schema.sql.
All paths below are **relative to repo root**.

---

## 1. Core Data Folders

| Path                    | Purpose                                                                                 | Rules |
|-------------------------|-----------------------------------------------------------------------------------------|-------|
| `data_raw/`             | Raw exports from Kaspi / WB / suppliers (ActiveOrders, ArchiveOrders, stock dumps).    | Never edit in place; treat as read-only snapshots. |
| `data_stage/`           | Cleaned / normalized CSVs ready for DB ingest (e.g. parsed ActiveOrders, sales).       | Can be regenerated at any time from `data_raw/`. |
| `db/`                   | SQLite databases and migrations (`app.db`, migration scripts).                         | Only code writes here; no manual edits. |
| `exports/`              | Outgoing reports (replenishment plans, PO drafts, weekly reports, alerts).             | Safe to share / send. |
| `logs/`                 | Runtime logs from scripts and services.                                                 | Rotatable; can be truncated/archived. |
| `backups/`              | Zipped backups of databases and important exports.                                      | Never auto-deleted without a clear policy. |

---

## 2. Business Logic / UI Folders

| Path                         | Purpose                                                         |
|------------------------------|-----------------------------------------------------------------|
| `excel_ui/`                  | Excel workbooks used as UI (e.g. `Inventory_Core_V15_FINAL.xlsx`). |
| `docs/`                      | High-level docs (strategy, workflows, protocols).              |
| `docs/protocol/`            | Operational docs (`MIGRATION_LOG.md`, `RULES.md`, `TASKS.md`).  |
| `scripts/`                   | High-level entrypoint scripts (ETL, audits, daily jobs).       |
| `config/`                    | YAML/TOML configs (API keys paths, store mappings, parameters). |

Recommended key files:

- `docs/protocol/MIGRATION_LOG.md` — migration tracking (this file’s sibling).
- `docs/protocol/RULES.md` — coding and automation rules.
- `docs/protocol/TASKS.yaml` — prioritized automation tasks.
- `config/paths.yaml` — additional machine-resolved paths if needed.

---

## 3. Principles

1. **Raw → Stage → DB → Exports**  
   - Every data flow should move in that direction. No script should write into `data_raw/`.

2. **Single source of truth per layer**  
   - Historical sales: DB (`fact_sales_raw`, `fact_sales_daily`), not random Excel files.
   - Inventory/ROP rules: `Master_Inventory_Rules_v5.3.md`.
   - Excel UI: `excel_ui/Inventory_Core_V15_FINAL.xlsx`.

3. **Relative paths only in code**  
   - Scripts should assume repo root and use relative paths (`data_raw/...`), not absolute `/Users/...`.

4. **Backups are sacred**  
   - Only explicit “backup rotation” scripts are allowed to delete from `backups/`.

