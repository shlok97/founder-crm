---
name: crm-capture-conversation
description: Capture founder-provided call or meeting notes into Founder CRM and propose supported next steps. Use when logging an actual conversation or importing a note; do not invent interactions.
---

Use `crm_intake_note` with a stable, user-meaningful external ID for the conversation. Reuse that ID on a retry; do not manufacture a fresh ID to bypass duplicate detection. Record what the user actually provided, separating their statement from your inference.

Match the relationship using `crm_dashboard` and `crm_account_history`. If identity is ambiguous or no account exists, ask for the right relationship or direct the user to add it in the dashboard; do not silently merge contacts or create a paying customer.

Stage next steps with `crm_propose_update`. `create_task` requires `account_id` and `title`, optionally `due_date` in YYYY-MM-DD. `log_interaction` requires `account_id` and `summary`. `open_ticket` requires `account_id` and `title`. Keep an expression of interest distinct from a confirmed demo, and a pilot request distinct from payment.

The tool only stages a proposal. Report its ID and pending status. Apply/reject controls belong to the local dashboard or human CLI; there is no MCP approval tool.
