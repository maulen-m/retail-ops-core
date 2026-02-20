# Transfer Ledger Governance

This folder is **script-generated only** for ledger snapshots and operational summaries.

Policy:
- `docs/transfer_ledger/*.md` are generated outputs; **no manual edits** are allowed.
- Source of truth is `db/app.db` + ingestion scripts; reports are render artifacts.
- Any report refresh must come from the canonical generator command below.
- Reviewers should validate report diffs against source DB/event changes, not edit report files directly.

Canonical generation command:
- `python3 scripts/generate_transfer_ledger_reports.py --db db/app.db --output-dir docs/transfer_ledger --days 0`

Determinism rules:
- Run with a fixed DB snapshot.
- Use explicit CLI flags (`--days 0` for full-history refresh).
- Keep sort keys deterministic in report SQL/render paths.

Commit discipline:
- Commit report updates together with the code or ingestion change that caused them.
- If no source/data change exists, do not commit regenerated ledger reports.
- In PR description, include generator command and DB snapshot context.

Rollback:
- `git revert <commit>` for accidental report churn.
- Regenerate from canonical command against the intended DB snapshot.
