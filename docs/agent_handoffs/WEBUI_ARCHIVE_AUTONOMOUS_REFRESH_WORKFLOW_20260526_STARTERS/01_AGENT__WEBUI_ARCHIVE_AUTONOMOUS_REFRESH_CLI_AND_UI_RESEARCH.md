# Agent: WebUI Archive Autonomous Refresh CLI and UI Research

## Mission
Make the WebUI ArchiveOrders refresh workflow autonomous, repeatable, and safe enough that future sales-freshness tasks know exactly which repo CLI/workflow to use.

## Read First
1. `AGENTS.md`
2. `docs/00_START_HERE.md`
3. `docs/validation/WEBUI_ARCHIVE_AUTONOMOUS_REFRESH_WORKFLOW.md`
4. `docs/validation/WEBUI_ARCHIVE_SINGLE_TRUTH_CONTRACT.md`
5. `docs/validation/KASPI_ARCHIVE_UI_PACK_CONTRACT.md`
6. `docs/validation/KASPI_ARCHIVE_API_PACK_CONTRACT.md`
7. `scripts/run_webui_archive_source_refresh.py`
8. `scripts/run_webui_archive_full_parse.py`
9. `scripts/playwright/download_kaspi_archive_webui.py`
10. `config/kaspi_stores.yaml`

## Owner Context
The owner manually downloaded WebUI archive examples under:

`imports/webui_archive_manual/26.05.2026_14_34_04`

The screenshots show the Kaspi Seller Cabinet Archive page with:
- archive URL state `status=ARCHIVED`;
- date range inputs limited to `90` days or less;
- `Применить` button;
- `Выгрузить в EXCEL` button;
- store/session context visible in the seller cabinet header.

Do not optimize only for LINE61 or LINE51. The autonomous route must fetch every order/product in the selected window for every enabled store unless the task explicitly narrows scope and records omissions.

## Allowed Work
- Inspect existing scripts and tests.
- Import the manual example as read-only evidence if useful.
- Use Chrome, Playwright, or Computer Use for visual/UI research and download-only automation only when the launch prompt contains the owner approval phrase.
- Patch the repo-owned CLI/downloader if selectors, datepicker handling, session handling, per-store session state, or manifest outputs are insufficient.
- Add focused tests for the workflow changes.
- Write local evidence and a closeout.

## Forbidden Work
- Do not write `db/app.db`.
- Do not mutate `excel_ui/SALES_KSP_CRM_V3.xlsx` or any workbook.
- Do not update source-pointer anchors.
- Do not change schedulers, LaunchAgents, or cron.
- Do not write to Web_automation.
- Do not perform Kaspi/API/WebUI mutations.
- Do not change orders, stock, prices, ads, bids, budgets, campaigns, cash, supplier payments, or PO commitments.
- Do not publish/send owner-facing outputs.
- Do not run production preflight or production apply.
- Do not print secrets from `.env`.

## Required Research Questions
Answer these in the closeout:

1. Does `scripts/run_webui_archive_source_refresh.py` already cover all enabled stores by default?
2. Does it split `since..until` into `90`-day-or-less blocks deterministically?
3. Does import-existing mode preserve source-file hashes and requested window provenance?
4. Does live WebUI mode correctly operate the current Kaspi UI date picker and Excel export button?
5. If Chrome AutoConnect/CDP is requested, is it supported by repo code or still fail-closed?
6. What is the fastest safe API archive companion route, and which truth fields may it not replace?
7. What exact command should future agents run for all-store/all-product source freshness?

## Preferred Commands
Smoke the CLI help first:

```bash
python3 scripts/run_webui_archive_source_refresh.py --help
python3 scripts/run_webui_archive_full_parse.py --help
```

Validate current manual example import for the stores that have files:

```bash
python3 scripts/run_webui_archive_source_refresh.py \
  --since 2026-03-01 \
  --until 2026-05-26 \
  --source-root imports/webui_archive_manual/26.05.2026_14_34_04 \
  --stores ACMEWEAR,STOREB \
  --mode import-existing \
  --strict
```

For authorized live acquisition, default to all enabled stores by omitting `--stores`:

```bash
python3 scripts/run_webui_archive_source_refresh.py \
  --since 2026-05-05 \
  --until 2026-05-25 \
  --mode headful-manual-login \
  --allow-manual-download \
  --strict
```

Use API archive only as supporting evidence:

```bash
python3 scripts/export_kaspi_archive_history.py \
  --since 2026-05-05 \
  --until 2026-05-25 \
  --out-dir exports/validation/webui_archive_autonomous_refresh_20260526/api_archive_20260505_to_20260525
```

## Test Expectations
Run the smallest relevant checks for any changes:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q \
  tests/test_run_webui_archive_full_parse.py \
  tests/test_run_webui_archive_source_refresh.py \
  tests/test_validate_webui_archive_pack_integrity.py \
  tests/test_validate_kaspi_archive_pack_integrity.py
```

If only docs are touched, run:

```bash
scripts/lint_docs.sh
```

## Closeout Location
Write the final closeout under:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-26_webui_archive_autonomous_refresh_workflow/`

The closeout must include:
- gate color;
- commands run;
- evidence paths;
- store/window coverage table;
- all omitted stores;
- whether protected surfaces stayed unchanged;
- next exact command for the April 23 stock re-anchor sales-gap repair.
