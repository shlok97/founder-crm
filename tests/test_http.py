import http.client
import json
import os
from pathlib import Path
import re
import tempfile
import threading
import unittest
from unittest.mock import patch

from founder_crm.core import Store
from founder_crm.web import make_server


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.store = Store(Path(cls.tmp.name) / "crm.db")
        cls.store.init()
        cls.server = make_server(cls.store, 0)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.port = cls.server.server_port

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.tmp.cleanup()

    def request(self, path="/", method="GET", body=None, headers=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        c.request(method, path, body, headers or {})
        r = c.getresponse()
        result = (r.status, dict(r.getheaders()), r.read())
        c.close()
        return result

    def csrf(self):
        return re.search(rb'name="crm-csrf" content="([a-f0-9]+)"', self.request()[2])[
            1
        ].decode()

    def test_html_has_csp_and_no_unexpanded_token(self):
        code, headers, body = self.request()
        self.assertEqual(code, 200)
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertNotIn(b"__CSRF__", body)

    def test_host_validation(self):
        self.assertEqual(self.request(headers={"Host": "evil.example"})[0], 403)

    def test_write_requires_csrf(self):
        self.assertEqual(
            self.request(
                "/api/accounts",
                "POST",
                '{"name":"Bad"}',
                {"Content-Type": "application/json"},
            )[0],
            403,
        )

    def test_foreign_origin_rejected_even_with_token(self):
        headers = {
            "Content-Type": "application/json",
            "X-CRM-CSRF": self.csrf(),
            "Origin": "https://evil.example",
        }
        self.assertEqual(
            self.request("/api/accounts", "POST", '{"name":"Bad"}', headers)[0], 403
        )

    def test_valid_dashboard_write(self):
        code, _, body = self.request(
            "/api/accounts",
            "POST",
            '{"name":"HTTP Example"}',
            {"Content-Type": "application/json", "X-CRM-CSRF": self.csrf()},
        )
        self.assertEqual(code, 200)
        self.assertIn("id", json.loads(body))

    def test_http_cannot_forge_trusted_gmail(self):
        payload = {
            "external_id": "forge",
            "subject": "Sent",
            "sender": "",
            "body": "Told them",
            "trusted": True,
            "source": "gmail",
        }
        code, _, _ = self.request(
            "/api/intake",
            "POST",
            json.dumps(payload),
            {"Content-Type": "application/json", "X-CRM-CSRF": self.csrf()},
        )
        self.assertEqual(code, 400)

    def test_payload_size_limit(self):
        self.assertEqual(
            self.request(
                "/api/intake",
                "POST",
                "x" * 65537,
                {"Content-Type": "application/json", "X-CRM-CSRF": self.csrf()},
            )[0],
            413,
        )

    def test_webhook_token_and_idempotent_intake(self):
        token = "a" * 40
        body = json.dumps(
            {
                "email": "form@forms.example",
                "message": "Hello",
                "submission_id": "same-form",
            }
        )
        with patch.dict(os.environ, {"FOUNDER_CRM_WEBHOOK_TOKEN": token}):
            self.assertEqual(
                self.request(
                    "/hooks/web3forms/wrong",
                    "POST",
                    body,
                    {"Content-Type": "application/json"},
                )[0],
                403,
            )
            one = self.request(
                "/hooks/web3forms/" + token,
                "POST",
                body,
                {"Content-Type": "application/json"},
            )
            two = self.request(
                "/hooks/web3forms/" + token,
                "POST",
                body,
                {"Content-Type": "application/json"},
            )
            self.assertEqual(one[0], 200)
            self.assertTrue(json.loads(two[2])["duplicate"])


if __name__ == "__main__":
    unittest.main()
