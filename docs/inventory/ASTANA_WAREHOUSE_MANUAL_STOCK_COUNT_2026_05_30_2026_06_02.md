# Astana Warehouse Manual Stock Count - 2026-05-30 to 2026-06-02

Status: owner-approved local physical stock count for the covered models/sizes.

Canonical machine-readable source:

- `config/anchors/manual_stock_counts/astana_warehouse_manual_stock_count_2026_05_30_2026_06_02.approved.json`
- `config/anchors/manual_stock_counts/astana_warehouse_manual_stock_count_2026_05_30_2026_06_02.approved_aggregate.csv`

The count was performed manually by the warehouse employee in Astana after the
respective day's shipments. The OCR outputs were compared across two agents and
the owner-confirmed correction was applied:

- `IMG_4797 copy.jpeg` / `Rombik_men` / `3XL` / `romb` is `21`, not `24`.

## Priority Rule

For any SKU-size row or shared stock pool explicitly covered by the approved
manifest, future inventory agents must use this manual count before older stock
anchors, reconstructed stock timelines, marketplace/Kaspi availability, and
OCR-only evidence.

After the count timestamp, stock may move only through trusted subsequent
events:

- delivered shipped sales after the count,
- confirmed inbound after the count,
- separately approved return or cancellation restock events after employee count.

Do not infer zero for sizes absent from the manifest.

## Duplicate Rows

If the same product size appears multiple times in the source images, the units
are summed. Example: Line61 `2XL` appears in both `IMG_4820.jpeg` and
`IMG_4821.jpeg`; the approved aggregate is `44 + 17 = 61`.

## Returns And Cancellations Caveat

Quarantine returns and cancellation units were not manually counted and are not
included in these snapshot quantities. They remain pending employee count and
must not be added, zeroed, or treated as approved sellable stock until separately
counted and approved.

## Totals

| Timestamp folder | Approved units |
| --- | ---: |
| `30.05.2026_21_19_00` | 212 |
| `01.06.2026_22_22_30` | 686 |
| `02.06.2026_18_00_36` | 935 |
| **Total** | **1833** |

## Validation

Use:

```bash
python3 -m core.ops.manual_stock_count_manifest
```

Expected output includes:

```text
aggregate_rows=39
total_units=1833
quarantine_returns_included=false
cancellation_units_included=false
```
