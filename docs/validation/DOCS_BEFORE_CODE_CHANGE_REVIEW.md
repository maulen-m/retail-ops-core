# Docs-Before-Code Change Review

## Purpose

`G-REPO-02` requires a deterministic review proving that business-rule changes update their owning docs in the same changeset. This review is a guardrail against stale plans or code becoming accidental authority.

## Contract

The review must:

- inspect changed tracked files and untracked source/config files;
- ignore mutable progress, runtime, export, test, and evidence files as authority changes;
- classify changed business-rule code/config into explicit domains;
- map each domain to one or more owning docs from `AGENTS.md` and `docs/00_START_HERE.md`;
- pass only when every classified business-rule domain has at least one owning doc changed in the same worktree;
- fail closed on changed business-rule code/config that does not match a known domain;
- emit a JSON/Markdown report with changed files, domain rows, blockers, and the final gate decision.

This report does not decide whether the business-rule edit is correct. It only proves the docs-before-code invariant for changed surfaces.

## Promotion Rule

`G-REPO-02` can move from `ARMED` to `GREEN` only when:

- `scripts/lint_docs_active_scope.py --strict` passes;
- this change-review report is `ok=true`;
- the report includes no unmatched business-rule files and no domains missing changed owning docs;
- normal repo guards for the touched files pass.

If any blocker remains, the gate stays `ARMED`.
