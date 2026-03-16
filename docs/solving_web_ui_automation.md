The immediate answer is: **do not do more profit/ads/COGS work on the WebUI path yet**. The current blocker is not the downstream math; it is that the **seed WebUI source is not yet usable as historical truth**. The seed pack fails integrity because **16,165 delivered rows are missing `status_change_at`**. The ledger continuity check still passes, but that only proves 90-day window coverage; it does **not** prove usable status timestamps. Right now the WebUI truth projection is effectively empty.   

That empty projection is why the rest of the WebUI stack is red: WebUI-vs-CRM shows **`floor_days=179`**, WebUI-vs-DB shows **`db_only_orders=2495`**, the audit table contains **only API observations** and **no WEBUI observations**, and owner publication is locked with `ADS_READINESS_FAIL`, `WEBUI_PROMOTION_FAIL`, and `WEBUI_PROJECTION_EMPTY`.    

So what has to be done is this, in order.

## 1) Prove whether the WebUI export itself is usable

This is the next required step. You need a **binary answer**:

* **Case A:** the raw WebUI files actually contain nonblank status-change timestamps for delivered rows, and the parser is losing them.
* **Case B:** the raw WebUI files themselves do **not** contain those timestamps, which means the current export variant is the wrong source for this migration.

Right now the evidence only proves that the **normalized pack** has blank `status_change_at` for delivered rows; it does **not** yet prove whether that is a raw-source problem or a parsing problem. Until that is known, everything downstream is noise.  

### What the agent should do next

For each of the 5 seed source files:

* count raw nonblank values in the exact source column for `Дата изменения статуса`,
* count raw nonblank values **specifically for delivered/completed rows**,
* compare those counts against normalized nonblank `status_change_at`,
* emit a single report like:

  * `raw_status_change_profile.csv`
  * `raw_vs_normalized_status_change_diff.csv`
  * `webui_source_viability_report.md`

### Success criterion

* If raw delivered rows have nonblank status-change timestamps, but normalized rows are blank, then this is a **parser defect** and the parser must be fixed.
* If raw delivered rows are blank too, then this is a **source defect** and the current WebUI export flavor cannot be promoted as primary historical truth.

## 2) If the source is wrong, stop the migration and get the correct export variant

If Case B is true, then the next thing to do is **not** more coding on band validators, ads, or owner review. The only meaningful human step is to obtain the **correct WebUI archive export variant** — the one that really includes status-locked timestamps for delivered rows.

That human step should stay minimal:

* manually download **one verified raw archive file per store** or at least one verified sample that proves the schema,
* then the agent re-runs normalization/integrity.

### Required gate after reseeding

* `validate_webui_archive_pack_integrity --strict` must PASS
* specifically:

  * `delivered_missing_status_change_date == 0`
  * or a clearly documented acceptable threshold if the contract is deliberately changed first

Until that passes, **do not** continue the WebUI promotion path.  

## 3) If the source is right and the parser is wrong, fix only the parser first

If Case A is true, then the agent should:

* patch the raw-file parser only,
* rebuild the seed pack,
* rebuild the ledger,
* re-run projection and promotion.

### Required gates after parser fix

These are the first meaningful green conditions:

* `ledger_delivered_orders > 0`
* `projected_rows > 0`
* `projected_orders_matched > 0`
* `validate_webui_archive_vs_crm_band --strict` PASS
* `validate_webui_archive_vs_current_db --strict` PASS or at least materially improved with explicit diff evidence
* `validate_order_status_audit_history --strict` PASS with `WEBUI > 0` and `API > 0`

Right now all of these are blocked because the projection is empty.    

## 4) Only after projection is non-empty should you resume ads / COGS / owner review

Do **not** spend more time debugging WebUI ads coverage, spend realism, COGS completeness, COGS realism, or owner publication while `projected_rows == 0`. Those failures are currently downstream consequences of the empty projection, not independent root causes.  

The correct order is:

1. source viability,
2. pack integrity,
3. ledger projection,
4. CRM/DB promotion band,
5. then ads + COGS,
6. then owner publication.

## 5) Separate from WebUI, clear the generic red blockers

Even if the WebUI source is fixed, you still will **not** have a full green chain until the pre-existing generic blockers are cleared.

These are the main ones still visible:

* `validate_params.py --strict --as-of 2026-03-06` is red because of the `on_delivery_freeze` residual balances. `system_doctor` is blocked at the truth layer on that check. 
* `ADS_SOURCE_STALE` is still red, so `OWNER_PNL` remains fail-closed even aside from the WebUI source problem.  
* several required artifacts are still missing for the `2026-03-06` chain: external snapshot parity, recent identity coverage, order entries freshness, returns economics, and cash reconciliation. Those missing artifacts are explicit stoplines. 

So there are really **two** red streams:

1. **WebUI source-quality red**
2. **generic governance / finance red**

The WebUI stream must be resolved first if you want to keep this architecture. The governance stream must be resolved before any full green promotion.

## 6) Do not mistake the current Playwright result for a solved automation path

The download-validation step passed, but it passed in **`mode=import-existing`**, which means the validation only proved that copied files were present and hashed correctly. It did **not** prove a real authenticated browser scrape/download is working end-to-end. So P4 scaffolding exists, but the blocker right now is still **source content**, not automation plumbing.  

## 7) Keep the current rollback anchor; do not retire old methods yet

The rollout evidence explicitly says this WebUI migration is **not green promotion evidence** and that the active rollback anchor remains the `2026-03-04` green owner-truth release. So do **not** leave all current methods behind yet. Keep:

* current `2026-03-04` owner-truth release as rollback anchor,
* CRM as floor/ceiling control,
* current DB-based owner publication locked/unlocked under existing fail-closed rules,
  until the WebUI source wins promotion gates. 

## Minimum practical next instruction to the agent

Give the agent this exact priority:

1. **Source forensics first**

   * prove raw-source blank vs parser blank for `Дата изменения статуса`
   * emit raw-vs-normalized nonblank counts by store/file/status

2. **Decision point**

   * if raw source blank → stop migration, request correct export variant
   * if raw source populated → fix parser and reseed pack

3. **Re-run only the source-promotion chain**

   * pack integrity
   * ledger continuity
   * WebUI vs CRM band
   * WebUI vs DB
   * order-status audit

4. **Only then** re-run:

   * ads coverage / spend realism
   * COGS completeness / realism
   * North Star owner review
   * OWNER_PNL

5. In parallel but still required before final green:

   * clear `on_delivery_freeze`
   * refresh ads source
   * regenerate missing identity / returns / cash artifacts

## What should not be done now

* Do **not** unlock owner publication.
* Do **not** spend more time on WebUI economics while projection is empty.
* Do **not** treat the current chronology improvement number as success; with `ledger_delivered_orders=0` and `projected_rows=0`, that metric is not decision-grade. 
* Do **not** retire CRM/statusdate/DB shadow paths yet.
