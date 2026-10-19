# Release review · 19 October 2026

**Scope: an early, single-user local starter.** The code supports integration;
the default clone runs with fictional records and no external account. It is not
a hosted CRM or a verified live-mailbox deployment.

## What the review found and fixed

- Optional adapter installation failed after the demo created a `data/` directory.
  Setuptools treated it as another top-level package. Packaging now explicitly
  includes only `founder_crm` and its schema/static resources. The wheel excludes
  runtime data and private configuration.
- MCP could start against an uninitialized database but its first read failed.
  Startup now initializes an empty database and preserves existing records.
- Sent Gmail matching checked `To` alone. `Cc` and `Bcc` are now included when
  deciding whether one known recipient can be matched. Multi-recipient messages
  remain unmatched. Boolean message limits are rejected before a request.
- Initial publication used browser uploads. Updates use authenticated Git over
  HTTPS with a documented pre-push privacy check and GitHub Actions.

## Checks and their limits

| Surface | Verified | Still needs operator setup |
|---|---|---|
| Dashboard + SQLite | Fresh demo, empty workspace, evidence/proposal/review/audit flow; localhost HTTP checks | Backups and any future multi-user hosting design |
| Installed Python package | Installation with optional adapters after demo data exists; console entry point; packaged schema, HTML, CSS and JS | Supported Python 3.11+ on each operator's machine |
| Claude MCP | Actual SDK stdio subprocess; empty-database first read; form evidence → proposal → human dashboard approval → same task visible in MCP | Register in the user's Claude client and use the same DB path |
| Gmail | Native GET request URL, query, auth header, MIME parsing, duplicates and recipient matching against synthetic responses | Google Desktop OAuth client, consent and a real readonly pull |
| Web3Forms | Actual local HTTP webhook with documented JSON fields, token checks, retry deduplication and MCP visibility | A supported paid plan and an HTTPS relay exposing only the hook |
| Jev | Native request structure for TypeSafe and OpenRouter; valid response, 401/429/malformed failures; always advisory | Operator's own key and enabled model sharing; live response and accuracy are unmeasured |
| Personalisation | Reviewed account-owner extension, migration tests and existing MCP/browser checks | Each further client-specific change still needs review |

The expanded base suite had **45 tests**, and the reviewed extension added five. Version 0.2 has 52 base tests; the owner extension is now built in.
The integration tests make no external model requests, import no private records
and incur no model cost. The human approval boundary remains intact.

Provider contracts were checked against the official
[Gmail list API](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/list),
[Web3Forms webhook documentation](https://docs.web3forms.com/getting-started/pro-features/webhooks),
[TypeSafe Choice documentation](https://docs.typesafe.ai/primitives/choice) and
[OpenRouter Decisions API](https://openrouter.ai/docs/api/api-reference/alphadecisions/submit-a-decisions-request).
See [setuptools package discovery](https://setuptools.pypa.io/en/stable/userguide/package_discovery.html)
for the packaging fix. Contracts can change; fixture tests do not establish live
account connectivity or model accuracy.

Use the [integration instructions](integrations.md) to connect your own services.
Use the [maintenance workflow](maintaining.md) for future Git pushes.
