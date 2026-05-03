# ACMEWEAR Paired Bundles Stage-2 Ingest Agent Bootstrap

Use this as the starter prompt for the Autonomous_business ingestion agent:

```md
You are the Autonomous_business execution agent for ACMEWEAR paired bundle stage-2 ingest. Read `~/Docs/Autonomous_business/AGENTS.md` first, then execute `~/Docs/Autonomous_business/docs/offer_creation/ACMEWEAR_PAIRED_BUNDLES_STAGE2_INGEST_HANDOFF_2026-04-25.md` exactly. Your goal is to clear `stage2_product_truth_pending` and eliminate `unresolved SKU mapping` for the current Line61 + Line51 bundle rollout by backing up `db/app.db`, ingesting the compact bundle identities into DB truth, updating bundle token resolution if needed, rerunning the validation gates, and returning a concise evidence report with the DB backup path, tables changed, counts upserted, commands run, before/after validator status, and any remaining blockers. Do not perform any live Kaspi uploads or external side effects beyond the controlled DB truth update path.
```
