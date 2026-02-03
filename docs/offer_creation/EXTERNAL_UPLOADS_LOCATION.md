# External storage for Kaspi offer upload ZIPs

Large ZIPs should not live in the repo. Store them externally at:

`~/Documents/useful tables/Main crm spreadsheets/main tables/External_database/kaspi_offer_uploads`

## Required structure

```
External_database/
  kaspi_offer_uploads/
    <MODEL>/
      <CATEGORY>/
        <YYYY-MM-DD_HHMMSS>/
          <ZIP files>
```

### Example

```
.../kaspi_offer_uploads/LINE61/men-thermal-underwear/2026-02-03_214550/ACMEWEAR_LINE61_THERMAL_V1_UPLOAD_20260203_214550.zip
```

## Notes
- Keep timestamps in local time.
- If a ZIP is regenerated, create a new timestamped folder (do not overwrite).
