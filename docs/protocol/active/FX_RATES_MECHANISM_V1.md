# FX Rates Mechanism V1

Status: active authority for Autonomous_business FX and supplier landed COGS.

Scope:
- Kaspi-only operating repo.
- FX inputs, cadence, fallback behavior, and landed-cost policy for COGS, cash, PO, inventory valuation, and future pricing-floor ratification.

Decision source:
- `OWNER_DECISIONS_RECORDED.yaml` OD-013.
- Owner-ratified source: owner actual Binance P2P or bank rates.
- Cadence: weekly entry by automation, with a verification line in the weekly owner digest.

## 1. Data Authority

The canonical FX table is `dim_fx_rates` in `db/app.db`.

Required effective-dated columns:

| Column | Meaning |
|---|---|
| `effective_date` | First date the row is valid for. |
| `usdt_kzt` | Actual KZT per USDT from owner funding path. |
| `usdt_cny` | Actual CNY per USDT from owner funding path. |
| `cny_kzt` | Stored convenience value; must match `usdt_kzt / usdt_cny` unless a forced exception is documented. |
| `usd_kzt` | USD/KZT for freight legs. |
| `dlv_rate_usd_kg` | Freight USD per kg. |
| `provider` | Source class, for example `OWNER_ACTUAL`. |
| `source` | Specific evidence/provenance label. |
| `updated_at` | Row write timestamp. |

`scripts/upsert_fx_rates.py` is the governed writer. It is dry-run by default, and production apply requires `ENABLE_FX_RATES_WRITE=1`, `--apply`, and `--backup-dir`.

## 2. Supplier Landed-COGS Resolution

Supplier landed COGS uses one runtime authority path:

- `core.config.business_params.get_supplier_fx_rates(...)` when resolving from a DB path.
- `core.config.business_params.get_supplier_fx_rates_from_conn(...)` when resolving from an existing SQLite connection.

Precedence:

1. Routed supplier FX from `dim_fx_rates`: `CNY_KZT = usdt_kzt / usdt_cny`.
2. Owner-approved fallback `CNY_KZT = 73` only when routed supplier FX is unavailable.

`usd_kzt` and `dlv_rate_usd_kg` come from the same effective-dated row when present; otherwise they fall back to the runtime defaults in `DEFAULT_FX_RATES`.

Legacy `75` and `78` values are not active supplier landed-cost truth. They may remain only as backwards-compatible defaults, seed/bootstrap compatibility, archived estimates, or explicitly labeled legacy fallbacks.

## 3. Landed-Cost Policy

Forward policy:

- Populate landed cost at receive time from invoice plus freight.
- Use routed supplier FX for the CNY leg.
- Use `usd_kzt` and `dlv_rate_usd_kg` for freight.
- Preserve row-level provenance for source, effective date, and fallback class.

Historical policy:

- Do not back-fabricate missing landed costs.
- Historical rows without sufficient source inputs remain `MISSING`, `unresolved`, or an explicit approved override/quarantine path.
- Owner-approved exact-row overrides must remain exact-row scoped and visible in their source labels.

## 4. Consumer Contract

Formula consumers must not maintain private supplier-FX constants for active landed COGS.

Allowed patterns:

- Use `get_supplier_fx_rates(...)` or `get_supplier_fx_rates_from_conn(...)`.
- Use `resolve_landed_cogs(...)` for row-level COGS calculation when base cost and weight are available.
- Preserve compatibility constants only when they are labeled as legacy defaults or non-supplier planning fallbacks.

Forbidden patterns:

- Treating `DEFAULT_FX_RATES["cny_kzt"]` as active supplier landed-cost truth.
- Promoting archived `75` or `78` estimates without a legacy label.
- Changing pricing-floor values inside the FX lane. `PKT-PRICE` owns floor ratification and price uploads.

## 5. Validation Surface

Minimum closeout checks for this authority:

- `scripts/upsert_fx_rates.py --show-latest`
- `python3 scripts/validate_policy_source_freshness.py`
- `python3 scripts/audit_cogs_realism.py --as-of <YYYY-MM-DD> --days 30`
- Focused tests for supplier-FX helper and active COGS consumers.
- Grep evidence that active landed-COGS consumers route through the authority helper or an explicitly documented compatibility fallback.

`scripts/lint_docs.sh` remains part of repo doc verification, but the current green-path program has a known baseline false positive on canonical evidence numbers. Do not rewrite evidence numbers to satisfy the linter.
