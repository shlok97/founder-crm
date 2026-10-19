"""Explicit adapters. Reading Gmail never modifies mail or downloads attachments."""

import base64
from email.utils import getaddresses
import json
import os
from pathlib import Path
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen

from .core import CRMError, digest


def gmail_token_path(store):
    return store.path.parent / "gmail-token.json"


def gmail_auth(store, client_secrets):
    """User-invoked OAuth. This command opens Google's normal consent flow."""
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as e:
        raise CRMError('Install the gmail extra: pip install -e ".[gmail]"') from e
    flow = InstalledAppFlow.from_client_secrets_file(
        client_secrets, ["https://www.googleapis.com/auth/gmail.readonly"]
    )
    credentials = flow.run_local_server(port=0)
    path = gmail_token_path(store)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(credentials.to_json())
    path.chmod(0o600)
    return {"authorized": True, "scope": "gmail.readonly", "token_file": str(path)}


def gmail_access_token(store):
    token = os.getenv("FOUNDER_CRM_GMAIL_ACCESS_TOKEN")
    if token:
        return token
    path = gmail_token_path(store)
    if path.exists():
        try:
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request as GoogleRequest

            credentials = Credentials.from_authorized_user_file(
                str(path), ["https://www.googleapis.com/auth/gmail.readonly"]
            )
            if credentials.expired and credentials.refresh_token:
                credentials.refresh(GoogleRequest())
                fd = os.open(path, os.O_WRONLY | os.O_TRUNC, 0o600)
                with os.fdopen(fd, "w") as f:
                    f.write(credentials.to_json())
            if credentials.valid:
                return credentials.token
        except Exception as e:
            raise CRMError(
                "Gmail credentials need attention. Run gmail-auth again; no mail was changed."
            ) from e
    raise CRMError(
        "Run gmail-auth with your Desktop OAuth client, or set FOUNDER_CRM_GMAIL_ACCESS_TOKEN."
    )


def receive_web3forms(store, payload):
    if not isinstance(payload, dict):
        raise CRMError("Expected a Web3Forms JSON object.")
    # These are never evidence or CRM fields; never retain form credentials.
    private = {
        "access_key",
        "apikey",
        "attachment",
        "botcheck",
        "recaptcha_response",
        "token",
        "webhook",
    }
    evidence = {k: v for k, v in payload.items() if k not in private}
    email = evidence.get("email", "")
    message = evidence.get("message", "")
    if (
        not isinstance(email, str)
        or "@" not in email
        or not isinstance(message, str)
        or not message.strip()
    ):
        raise CRMError("A form submission needs email and message fields.")
    return store.ingest(
        "web3forms",
        str(evidence.get("submission_id") or digest(evidence)),
        str(evidence.get("subject") or "Website enquiry"),
        email,
        json.dumps(evidence, ensure_ascii=False),
    )


def gmail_text(payload):
    if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
        data = payload["body"]["data"]
        return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode(
            "utf-8", errors="replace"
        )
    parts = [gmail_text(p) for p in payload.get("parts", [])]
    return "\n".join(p for p in parts if p)


def sync_gmail(store, query="in:inbox newer_than:14d", limit=20, *, fetch=None):
    if not isinstance(limit, int) or not 1 <= limit <= 50:
        raise CRMError("Gmail pull limit must be 1–50 messages.")
    if not isinstance(query, str) or len(query) > 1000:
        raise CRMError("Invalid Gmail query.")
    if fetch is None:
        token = gmail_access_token(store)

        def fetch(path):
            req = Request(
                "https://gmail.googleapis.com/gmail/v1/users/me/" + path,
                headers={"Authorization": "Bearer " + token},
            )
            try:
                with urlopen(req, timeout=25) as r:
                    return json.loads(r.read())
            except Exception as e:
                raise CRMError(
                    "Gmail pull failed. Check the access token and readonly scope; no mail was changed."
                ) from e

    page = fetch("messages?" + urlencode({"q": query, "maxResults": limit}))
    results = []
    # Pull a bounded page. Re-running is safe: provider message IDs are deduplicated.
    for item in page.get("messages", [])[:limit]:
        id = item.get("id")
        if not isinstance(id, str):
            raise CRMError("Gmail returned an invalid message ID.")
        msg = fetch("messages/" + quote(id, safe="") + "?format=full")
        headers = {
            h["name"].lower(): h["value"]
            for h in msg.get("payload", {}).get("headers", [])
        }
        outbound = "SENT" in msg.get("labelIds", [])
        raw = headers.get("to" if outbound else "from", "")
        addresses = [address.lower() for _, address in getaddresses([raw])]
        # Multi-recipient mail cannot attest a notification to one known contact.
        sender = addresses[0] if len(addresses) == 1 else ""
        body = (
            gmail_text(msg.get("payload", {}))
            or msg.get("snippet")
            or "(No plain-text message available.)"
        )
        results.append(
            store.ingest(
                "gmail",
                id,
                headers.get("subject") or "(No subject)",
                sender,
                body[:20000],
                direction="out" if outbound else "in",
                trusted=True,
            )
        )
    return {
        "received": len(results),
        "new": sum(not r["duplicate"] for r in results),
        "duplicates": sum(r["duplicate"] for r in results),
        "has_more": bool(page.get("nextPageToken")),
        "note": "Bounded read-only page; repeat with a narrower date query to review other windows.",
    }
