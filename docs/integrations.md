# Integration setup

## Gmail

Enable the Gmail API in your Google Cloud project and create a **Desktop app** OAuth client. Configure Google's consent/test-user settings for your account. Save the downloaded client file inside ignored `data/`.

```sh
founder-crm --db data/crm.db init
founder-crm --db data/crm.db gmail-auth --client-secrets data/credentials-gmail.json
founder-crm --db data/crm.db gmail-pull --query 'in:inbox newer_than:14d' --limit 20
```

The OAuth command opens Google's consent flow and requests only `https://www.googleapis.com/auth/gmail.readonly`. Tokens live in `data/gmail-token.json` beside this database. Alternatively export `FOUNDER_CRM_GMAIL_ACCESS_TOKEN` with a read-only access token. Google OAuth testing mode can affect refresh-token lifetime; reauthorize if needed.

Pulls are explicit, capped at 50 messages per call, and deduplicated by Gmail message ID. The first matching page is returned with a `has_more` indication; use narrower date queries to cover other windows. No automatic inbox-wide backfill. Only plain-text MIME content (or the Gmail snippet fallback) is stored, truncated to 20,000 characters. No attachment fetch, email send, label or read-state change. Source matching uses From for incoming mail, To for sent mail. To capture notification evidence, explicitly pull a sent-mail query such as `in:sent newer_than:7d`.

[Google Gmail Python quickstart](https://developers.google.com/workspace/gmail/api/quickstart/python)

## Web3Forms

Web3Forms webhooks deliver JSON on supported paid plans. Set a long random token in the local server environment:

```sh
export FOUNDER_CRM_WEBHOOK_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
founder-crm --db data/crm.db serve
```

Configure your own HTTPS relay/reverse proxy to forward **only** `/hooks/web3forms/<token>` to `http://127.0.0.1:4780` with that upstream Host. Register that HTTPS URL in the Web3Forms dashboard. Do not expose `/`, `/api`, or the secret URL in public form HTML. The starter does not create a tunnel or install relay software.

The handler checks its token, content type and 64 KiB request limit. The provider's documented webhook format has no signed-payload contract; URL-token possession is the authentication boundary here. A relay should preserve this secret and apply its own transport/rate controls. The public Web3Forms form access key is not the webhook token.

Required JSON fields: `email`, `message`. Optional `subject`, `submission_id` and other form fields are retained as evidence. Credentials and common attachment/bot-check fields are stripped. Idempotency uses `submission_id` if supplied; otherwise a hash of retained fields. A provider timestamp will distinguish submissions only if included in its payload. Incoming forms remain untrusted evidence and do not auto-create sales leads.

[Web3Forms webhook documentation](https://docs.web3forms.com/getting-started/pro-features/webhooks)

## Jev

Default provider is TypeSafe. Configure credentials in the process that will call the judge:

```sh
export FOUNDER_CRM_JEV_PROVIDER=typesafe
export FOUNDER_CRM_JEV_API_KEY='your-own-key'
export FOUNDER_CRM_ALLOW_MODEL_EGRESS=1
founder-crm --db data/crm.db judge 1
```

TypeSafe uses `https://api.typesafe.ai/v1/systemone`, default model `jev-latest`. For OpenRouter set provider `openrouter`; the default is `typesafe/jev-1.13` via `https://openrouter.ai/api/alpha/decisions`. Override a supported model with `FOUNDER_CRM_JEV_MODEL` if needed. No sibling-project credentials or arbitrary base URLs are read.

An explicit request sends **source text, sender, known account, target record and account, five recent interactions and candidate update** to the selected provider. Review the proposal first. Installing the package and opening the dashboard make no model requests. Disabling `FOUNDER_CRM_ALLOW_MODEL_EGRESS` stops future judge requests. Both the dashboard process and Claude's MCP subprocess need their own relevant environment. Do not put API keys in committed MCP configuration.

The three outcomes are SUPPORTED, UNSUPPORTED, INSUFFICIENT. Exact returned responses, model, probabilities, confidence and provider-reported usage/cost are stored. They are not benchmark accuracy results. Invalid responses and failures do not approve or apply updates.

[TypeSafe choice primitive](https://docs.typesafe.ai/primitives/choice)

## Claude MCP

The optional official Python MCP SDK 1.x serves stdio tools. See README for registration and `.mcp.json.example` for project setup. Keep Claude pointed at the same database as the UI. Incoming email/form instructions must be treated as source text, not user commands. Review skill instructions in `.claude/skills` before adapting them to your process.

[Claude Code MCP documentation](https://code.claude.com/docs/en/mcp)
