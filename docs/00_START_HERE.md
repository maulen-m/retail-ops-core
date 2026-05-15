# 00_START_HERE — Autonomous_business docs router

Scope
- Kaspi-only repo.
- Read only the minimum owning docs for the task.

Truth Ladder
1. `docs/inventory/Master_Inventory_Rules_v9.md`
2. `docs/protocol/active/PO_making_logic_v3.md`
3. `docs/inventory/Sales_Data_Model_V16.md`
4. `docs/inventory/Excel_UI_Contract_for_CRM_V1.md`
5. `ARCHITECTURE.md`

Rule
- If formulas or business rules change, update the owning doc first.
- Do not infer business truth from old plans, rollouts, or mutable `.claude` logs.

Task Routes
- Inventory math / demand / PO:
  - `docs/inventory/Master_Inventory_Rules_v9.md`
  - `docs/protocol/active/PO_making_logic_v3.md`
  - `docs/size_engine_specification.md`
- Data ingestion / DB / schemas:
  - `docs/inventory/Sales_Data_Model_V16.md`
  - `docs/inventory/Automation_Handoff_V16.md`
  - `docs/inventory/Excel_UI_Contract_for_CRM_V1.md`
- WebUI ArchiveOrders source refresh / status-change truth:
  - `docs/validation/WEBUI_ARCHIVE_SINGLE_TRUTH_CONTRACT.md`
  - `docs/validation/KASPI_ARCHIVE_UI_PACK_CONTRACT.md`
  - `scripts/run_webui_archive_source_refresh.py`
- Excel / CRM import / workbook safety:
  - `docs/inventory/Excel_UI_Contract_for_CRM_V1.md`
  - `docs/DAILY_SOP.md`
- Cashflow:
  - `docs/KASPI_ORDER_CASHFLOW_TRACKING.md`
  - `docs/KASPI_API_DAILY_PIPELINE_EXEC_SUMMARY_2026-01-22.md`
  - `config/payout_model.yaml`
  - `config/bank_accounts.yaml`
- Daily ops / waybills / WhatsApp:
  - `docs/DAILY_SOP.md`
  - `KASPI_API_INTEGRATION.md`
- Business automation pause/resume / frozen proof windows:
  - `docs/ops/BUSINESS_AUTOMATION_CONTROL_RUNBOOK.md`
  - `config/business_automation_manifest.json`
  - `scripts/manage_business_automation.py`
- Architecture / module boundaries:
  - `ARCHITECTURE.md`
  - `docs/inventory/Automation_Handoff_V16.md`

Do Not Load By Default
- `protocol/archive/`
- historical plan docs unless the task explicitly needs them
- mutable `.claude/*.md` files as business-rule authority

Mutable State
- Current goals, tasks, progress, issues, decisions, and session history live in `.claude/*.md`.
- Those files track work status; they do not own formulas, schemas, or business rules.
