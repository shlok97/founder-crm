# A real personalisation test

On 19 October 2026, Claude Code was asked to adapt a source-only copy of this starter for a small design agency. The request was to add an optional account owner, make it editable in the relationship form, expose it in existing MCP reads, and preserve old SQLite records. Only fictional demo/source data was supplied; private Altys records and credentials were excluded.

Claude changed the schema, store, CLI and dashboard. It reached its budget stop before finishing validation. Its first version failed an independent populated-database upgrade check: `Store.init` skipped its migration, leaving existing accounts without the new column. Review also preserved the positional audit-actor argument and corrected the CLI to pass owner by keyword.

Those corrections were made locally, with regression tests. The reviewed copy passes 44 tests, plus independent checks for idempotent upgrades, existing contact/task preservation, unknown owners staying NULL, new owner persistence and actual MCP stdio reads. A browser check added a fictional relationship with an owner, reloaded the page and reopened it successfully. No private CRM data or actual customer system was changed by this exercise.

The resulting [agency owner patch](examples/agency-owner.patch) contains the implementation and migration fixture/tests. On a clean copy of this version:

```sh
git apply --check docs/examples/agency-owner.patch
git apply docs/examples/agency-owner.patch
python -m founder_crm --db data/crm.db init
python -m unittest discover -s tests -v
```

Back up an existing database first. Pending proposals frozen before a schema/context change may need fresh proposals; do not rewrite their evidence to force them through.

This establishes one reviewed customisation, not unattended reliability for arbitrary client requests. The practical experience should include an understandable request, a copy/backup, tests, and a visible result. Claude's code is useful, and the review caught a real defect.

The authoring run reached its budget stop before validation. Follow-up corrections and verification were performed locally, without additional model calls.
