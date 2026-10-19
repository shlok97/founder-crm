# Founder CRM

Read README.md and docs/architecture.md before changing workflow behavior. This is an independent, local-first starter. Never import data, credentials or private configuration from sibling repositories.

Core code uses Python 3.11+ and the standard library. The optional MCP adapter targets the official MCP Python SDK 1.x. Run `python -m unittest discover -s tests -v` after changes to persistence, adapters or review behavior. MCP tests require the optional extra.

Keep intake evidence and proposed updates separate. Preserve idempotency and the human approval boundary. Investor/vendor relationships are not customer sales opportunities. Fixed and notified are separate states. Unknown facts remain unknown. Model/provider errors must leave proposals pending.

Demo records, docs and public screenshots must use synthetic people and `.example` addresses. All real data and credentials belong under ignored `data/` or explicitly configured private paths. Do not commit databases or publish the repository without the user's request.
