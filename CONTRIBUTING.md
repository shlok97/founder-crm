# Contributing

Start with a concrete founder workflow or a reproducible bug. Open an issue before building a large feature. Use fictional people and `.example` email addresses in issues, fixtures and screenshots.

Core dashboard and CLI use Python 3.11+ and the standard library. MCP and Gmail OAuth are optional extras. Keep input evidence separate from proposed updates, preserve the human approval boundary, and keep missing facts unknown.

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[mcp,gmail]'
python -m unittest discover -s tests -v
node --check loop_crm/static/app.js
```

Explain what changed and the check that demonstrates it. Schema changes need both fresh-database and populated-database upgrade coverage. Do not commit local databases, tokens, `.env` files or real messages. See [architecture](docs/architecture.md) and [the reviewed personalisation example](docs/personalisation-test.md).
