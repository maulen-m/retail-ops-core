# Owner Truth Anchor Bootstrap

## Purpose

Provide one explicit bootstrap/validate path for the live owner-truth anchors used by fail-closed runtime checks.

## Required Anchors

- `config/anchors/SALES_KSP_CRM_LATEST.xlsx`
- `config/anchors/INBOUND_CALENDAR_LATEST.xlsx`
- `config/anchors/STOCK_SNAPSHOT_LATEST.xlsx`
- `.env`
- `exports/validation/ads_scope_closeout/<AS_OF>`

## Bootstrap

```bash
python3 scripts/bootstrap_owner_truth_anchors.py \
  --project-root <REPO_PATH> \
  --crm-workbook <PATH_TO_CRM_WORKBOOK> \
  --inbound-workbook <PATH_TO_INBOUND_WORKBOOK> \
  --stock-workbook <PATH_TO_STOCK_WORKBOOK> \
  --env-file <PATH_TO_ENV_FILE> \
  --release-as-of <AS_OF> \
  --release-validation-root <PATH_TO_RELEASE_VALIDATION_ROOT>
```

## Validate Existing Anchors

```bash
python3 scripts/bootstrap_owner_truth_anchors.py \
  --project-root <REPO_PATH> \
  --validate-only

python3 scripts/check_anchor_health.py --project-root <REPO_PATH>
```

## Rules

- no implicit target discovery during bootstrap
- missing inputs fail closed
- live proving requires `.env` with store `KASPI_TOKEN_*` keys present
- replay proving for a frozen release requires the matching release validation root to be bootstrapped explicitly
- `scripts/check_anchor_health.py` remains the authoritative runtime health validator
