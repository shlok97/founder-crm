"""Offline provider contracts and real local HTTP/MCP interoperability.

Provider responses are synthetic. Nothing here calls an external account or model.
"""

import base64
import copy
import http.client
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

from loop_crm.core import CRMError, Store
from loop_crm.integrations import sync_gmail
from loop_crm.judge import judge_proposal
from loop_crm.web import make_server


def choice_response():
    return {
        "model": "jev-1.13.0",
        "answers": {"supported": {
            "type": "choice", "choice": "SUPPORTED", "confidence": 0.8,
            "probabilities": {"SUPPORTED": 0.9, "UNSUPPORTED": 0.05, "INSUFFICIENT": 0.05},
        }},
        "usage": {"input_tokens": 100, "output_tokens": 20},
    }


def json_response(value):
    return io.BytesIO(json.dumps(value).encode())


class ProviderContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name) / "crm.db")
        self.store.init()
        self.account = self.store.add_account("Contract Studio", "customer")["id"]
        self.store.add_contact(self.account, "Demo Person", "person@studio.example")
        note = self.store.ingest("claude_code", "call", "Call", "", "Offer two possible times.")
        self.proposal = self.store.propose(note["id"], "create_task", {
            "account_id": self.account, "title": "Offer two times",
        })["id"]

    def test_jev_native_requests_for_both_providers(self):
        providers = {
            "typesafe": ("https://api.typesafe.ai/v1/systemone", "jev-latest"),
            "openrouter": ("https://openrouter.ai/api/alpha/decisions", "typesafe/jev-1.13"),
        }
        for provider, (endpoint, model) in providers.items():
            with self.subTest(provider=provider), patch.dict(os.environ, {
                "LOOP_CRM_JEV_PROVIDER": provider,
                "LOOP_CRM_JEV_API_KEY": "synthetic-test-key",
                "LOOP_CRM_ALLOW_MODEL_EGRESS": "1",
                "LOOP_CRM_JEV_MODEL": "",
            }), patch("loop_crm.judge.urlopen", return_value=json_response(choice_response())) as send:
                result = judge_proposal(self.store, self.proposal)
                request = send.call_args.args[0]
                self.assertEqual(request.full_url, endpoint)
                self.assertEqual(request.get_method(), "POST")
                self.assertEqual(request.get_header("Authorization"), "Bearer synthetic-test-key")
                payload = json.loads(request.data)
                self.assertEqual(payload["model"], model)
                self.assertEqual(payload["questions"]["supported"]["type"], "choice")
                self.assertEqual(payload["state"]["evidence"], self.store.proposal(self.proposal)["context"])
                self.assertFalse(result["applied"])
                self.assertIsNone(result["cost_usd"])
                self.assertEqual(self.store.proposal(self.proposal)["status"], "pending")

    def test_jev_auth_rate_limit_and_invalid_json_leave_pending(self):
        failures = [HTTPError("https://provider.example", code, "Synthetic", {}, None) for code in (401, 429)]
        failures.append(json.JSONDecodeError("Synthetic malformed response", "", 0))
        for failure in failures:
            with self.subTest(failure=type(failure).__name__), patch.dict(os.environ, {
                "LOOP_CRM_JEV_API_KEY": "synthetic-test-key",
                "LOOP_CRM_ALLOW_MODEL_EGRESS": "1",
            }), patch("loop_crm.judge.urlopen", side_effect=failure):
                with self.assertRaises(CRMError):
                    judge_proposal(self.store, self.proposal)
        p = self.store.proposal(self.proposal)
        self.assertEqual(p["status"], "pending")
        self.assertEqual(p["judgments"], [])
        self.assertEqual(self.store.dashboard()["tasks"], [])

    def test_gmail_native_get_requests_query_mime_and_duplicates(self):
        message = {
            "labelIds": ["INBOX"],
            "payload": {"mimeType": "text/plain", "headers": [
                {"name": "From", "value": "Demo <PERSON@STUDIO.EXAMPLE>"},
                {"name": "Subject", "value": "A question"},
            ], "body": {"data": base64.urlsafe_b64encode(b"Please follow up.").decode()}},
        }
        requests = []
        def send(request, timeout):
            requests.append(request)
            self.assertEqual(request.get_method(), "GET")
            self.assertEqual(request.get_header("Authorization"), "Bearer synthetic-mail-token")
            u = urlsplit(request.full_url)
            self.assertEqual(u.netloc, "gmail.googleapis.com")
            if u.path.endswith("/messages"):
                self.assertEqual(parse_qs(u.query), {"q": ["in:inbox newer_than:1d"], "maxResults": ["1"]})
                return json_response({"messages": [{"id": "test-message"}], "nextPageToken": "next"})
            self.assertTrue(u.path.endswith("/messages/test-message"))
            self.assertEqual(parse_qs(u.query), {"format": ["full"]})
            return json_response(message)
        with patch.dict(os.environ, {"LOOP_CRM_GMAIL_ACCESS_TOKEN": "synthetic-mail-token"}), patch("loop_crm.integrations.urlopen", side_effect=send):
            first = sync_gmail(self.store, "in:inbox newer_than:1d", 1)
            second = sync_gmail(self.store, "in:inbox newer_than:1d", 1)
        self.assertEqual((first["new"], second["duplicates"]), (1, 1))
        self.assertTrue(first["has_more"])
        self.assertEqual(len(requests), 4)
        with self.store.connection() as c:
            row = dict(c.execute("SELECT * FROM intake WHERE source='gmail'").fetchone())
        self.assertEqual(row["body"], "Please follow up.")
        self.assertIsNotNone(row["contact_id"])

    def test_gmail_copied_recipients_remain_unmatched(self):
        for copied_header in ("Cc", "Bcc"):
            message = {"labelIds": ["SENT"], "snippet": "Export fixed.", "payload": {"headers": [
                {"name": "To", "value": "person@studio.example"},
                {"name": copied_header, "value": "other@other.example"},
            ]}}
            def fetch(path):
                return {"messages": [{"id": copied_header}]} if path.startswith("messages?") else copy.deepcopy(message)
            sync_gmail(self.store, fetch=fetch)
        with self.store.connection() as c:
            rows = c.execute("SELECT contact_id,sender FROM intake WHERE source='gmail'").fetchall()
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(r["contact_id"] is None and r["sender"] == "" for r in rows))

    def test_gmail_boolean_limit_refused_before_network(self):
        with patch("loop_crm.integrations.urlopen") as send, self.assertRaises(CRMError):
            sync_gmail(self.store, limit=True)
        send.assert_not_called()


@unittest.skipUnless(importlib.util.find_spec("mcp"), "Install the mcp extra for interoperability tests")
class InteroperabilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_new_database_forms_mcp_judge_and_human_dashboard(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {
            "LOOP_CRM_WEBHOOK_TOKEN": "synthetic-hook-token-" * 3,
            "LOOP_CRM_JEV_PROVIDER": "typesafe",
            "LOOP_CRM_JEV_API_KEY": "synthetic-test-key",
            "LOOP_CRM_ALLOW_MODEL_EGRESS": "1",
            "LOOP_CRM_JEV_MODEL": "",
        }):
            db = Path(tmp) / "fresh.db"
            params = StdioServerParameters(command=sys.executable, args=["-m", "loop_crm", "--db", str(db), "mcp"], env={**os.environ, "LOOP_CRM_ALLOW_MODEL_EGRESS": "0"})
            async with stdio_client(params) as (reader, writer):
                async with ClientSession(reader, writer) as session:
                    await session.initialize()
                    empty = await session.call_tool("crm_dashboard", {})
                    self.assertFalse(empty.isError)
                    self.assertEqual(json.loads(empty.content[0].text)["counts"]["accounts"], 0)
                    store = Store(db)
                    server = make_server(store, 0)
                    thread = threading.Thread(target=server.serve_forever, daemon=True)
                    thread.start()
                    def request(path, payload=None):
                        conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
                        conn.request("POST" if payload is not None else "GET", path, json.dumps(payload) if payload is not None else None, {"Content-Type": "application/json", "X-CRM-CSRF": csrf} if payload is not None else {})
                        response = conn.getresponse()
                        result = response.status, response.read()
                        conn.close()
                        return result
                    try:
                        csrf = re.search(rb'name="crm-csrf" content="([a-f0-9]+)"', request("/")[1])[1].decode()
                        status, body = request("/api/accounts", {"name": "Workflow Studio", "relationship": "prospect"})
                        self.assertEqual(status, 200)
                        account = json.loads(body)["id"]
                        self.assertEqual(request("/api/contacts", {"account_id": account, "name": "Demo Person", "email": "person@workflow.example"})[0], 200)
                        form = {"email": "person@workflow.example", "message": "Could you send two times for a demo?", "submittedAt": "2026-10-19T10:00:00Z"}
                        hook = "/hooks/web3forms/" + os.environ["LOOP_CRM_WEBHOOK_TOKEN"]
                        status, body = request(hook, form)
                        self.assertEqual(status, 200)
                        intake = json.loads(body)["id"]
                        self.assertTrue(json.loads(request(hook, form)[1])["duplicate"])
                        result = await session.call_tool("crm_propose_update", {"intake_id": intake, "action": "create_task", "payload": {"account_id": account, "title": "Offer two possible times"}})
                        self.assertFalse(result.isError)
                        proposal = json.loads(result.content[0].text)["id"]
                        with patch("loop_crm.judge.urlopen", return_value=json_response(choice_response())):
                            self.assertEqual(request("/api/judge", {"id": proposal})[0], 200)
                        self.assertEqual(store.dashboard()["tasks"], [])
                        self.assertEqual(store.proposal(proposal)["status"], "pending")
                        self.assertEqual(request("/api/apply", {"id": proposal, "confirm": True})[0], 200)
                        visible = await session.call_tool("crm_dashboard", {})
                        dashboard = json.loads(visible.content[0].text)
                        self.assertEqual(dashboard["tasks"][0]["title"], "Offer two possible times")
                        self.assertEqual(store.proposal(proposal)["status"], "applied")
                        self.assertEqual(json.loads(dashboard["audit"][0]["detail"])["human_review"], True)
                    finally:
                        server.shutdown()
                        server.server_close()
                        thread.join()
