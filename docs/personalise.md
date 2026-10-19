# Personalise a copy with Claude

Before changing code, check whether a custom field covers it. Custom fields hold your own data on any record, are type-checked, and can be marked as qualification questions; the dashboard's **Make it yours** view and `founder-crm field define` create them with no schema change. See [Make it yours](../README.md#make-it-yours). Change the code when you need a new rule, a new view, or a field that deserves a column of its own.

Open your own checkout in Claude Code. Start with the fictional demo before adding real records. The project includes `CLAUDE.md`, operating rules and three skills; use the MCP setup in README when you also want Claude to read or stage updates against the running database.

A useful first prompt describes your business and one concrete change:

> I run a small design agency. Add an optional owner to each relationship so I know who owes the next step. Let me enter it in the dashboard and see it through the existing Claude MCP reads. Preserve existing records when upgrading SQLite. Keep missing owners unknown, and preserve proposal review and the separate investor/vendor relationships. Add tests and run them. Explain the files you changed.

For a smaller visual change:

> Make this CRM feel like our agency: change the app name and accent colour, and use “Clients and partners” for Relationships. Keep the existing records, API and approval flow intact. Show me the result in the browser.

## Where changes belong

| Change | Files to inspect |
|---|---|
| Name, labels, layout and colours | `founder_crm/static/index.html`, `app.js`, `style.css` |
| Your own data on a record | Nothing: define a custom field |
| A new built-in field | `schema.sql` and `EDITABLE` in `core.py` (`Store.init` rebuilds changed tables), its dashboard/detail forms, a test |
| A new input channel | `integrations.py`, an explicit CLI or bounded server route, fixture tests |
| A new action | payload validation, propose/apply transaction and audit, MCP description, review UI, tests |
| How Claude should operate | `.claude/skills/` and `CLAUDE.md` |

SQLite `CREATE TABLE IF NOT EXISTS` does not add columns to an existing table. From 0.2, `Store.init` compares each table with `schema.sql`, copies any changed table into its new definition (refusing to drop a column), and writes a backup first; add the column to `schema.sql` and test the upgrade on a populated copy. Keep a backup and verify an upgrade on a populated copy. Check that unknown values remain NULL and existing pending proposals are either still valid or explicitly require re-proposal; do not silently rewrite frozen evidence.

The dashboard and MCP mostly read records through `Store`; include the new field in those responses rather than building a second store. Run `python -m unittest discover -s tests -v`, check browser JavaScript with `node --check founder_crm/static/app.js`, then exercise the actual form and reopen the record. A passing code change is a useful starting point; it does not prove another team's complete workflow fits.

External credentials and private records are not needed for this exercise. Connecting Gmail, Web3Forms or Jev is a separate step in [integration setup](integrations.md).

We ran the agency-owner exercise through Claude Code and independently tested the result. Its first pass needed a migration correction; the reviewed example passes 44 tests. See the [test and reusable patch](personalisation-test.md).
