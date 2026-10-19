import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
from urllib.parse import urlsplit

from .core import CRMError
from .integrations import receive_web3forms, sync_gmail, gmail_token_path
from .judge import judge_proposal


def make_server(store, port=4780):
    csrf = secrets.token_hex(32)
    static = Path(__file__).with_name("static")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            # Webhook capability tokens and private URLs never enter access logs.
            pass

        def send(self, code, value, kind="application/json"):
            data = (
                json.dumps(value, ensure_ascii=False).encode()
                if kind == "application/json"
                else value
            )
            self.send_response(code)
            self.send_header("Content-Type", kind + "; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'",
            )
            self.end_headers()
            self.wfile.write(data)

        def allowed_host(self):
            return self.headers.get("Host") in {
                f"127.0.0.1:{self.server.server_port}",
                f"localhost:{self.server.server_port}",
            }

        def do_GET(self):
            if not self.allowed_host():
                return self.send(403, {"error": "Invalid host."})
            path = urlsplit(self.path).path
            try:
                if path == "/api/dashboard":
                    data = store.dashboard()
                    with store.connection() as c:
                        data["demo"] = bool(
                            c.execute("SELECT 1 FROM meta WHERE key='demo'").fetchone()
                        )
                    data["integrations"] = {
                        "gmail_configured": bool(
                            os.getenv("FOUNDER_CRM_GMAIL_ACCESS_TOKEN")
                            or gmail_token_path(store).exists()
                        ),
                        "jev_configured": bool(os.getenv("FOUNDER_CRM_JEV_API_KEY")),
                        "model_sharing": os.getenv("FOUNDER_CRM_ALLOW_MODEL_EGRESS")
                        == "1",
                        "forms_configured": bool(
                            os.getenv("FOUNDER_CRM_WEBHOOK_TOKEN")
                        ),
                    }
                    return self.send(200, data)
                if path.startswith("/api/proposals/"):
                    return self.send(200, store.proposal(int(path.split("/")[-1])))
                if path.startswith("/api/accounts/"):
                    return self.send(
                        200, store.account_history(int(path.split("/")[-1]))
                    )
                assets = {
                    "/": ("index.html", "text/html"),
                    "/app.js": ("app.js", "application/javascript"),
                    "/style.css": ("style.css", "text/css"),
                }
                if path in assets:
                    name, kind = assets[path]
                    data = (static / name).read_bytes()
                    if name == "index.html":
                        data = data.replace(b"__CSRF__", csrf.encode())
                    return self.send(200, data, kind)
                return self.send(404, {"error": "Not found."})
            except (CRMError, ValueError) as e:
                return self.send(400, {"error": str(e)})

        def do_POST(self):
            if not self.allowed_host():
                return self.send(403, {"error": "Invalid host."})
            path = urlsplit(self.path).path
            hook = path.startswith("/hooks/web3forms/")
            if hook:
                token = os.getenv("FOUNDER_CRM_WEBHOOK_TOKEN", "")
                supplied = path.removeprefix("/hooks/web3forms/")
                if len(token) < 32 or not hmac.compare_digest(supplied, token):
                    return self.send(403, {"error": "Invalid webhook credential."})
            else:
                origin = self.headers.get("Origin")
                if origin and origin not in {
                    f"http://127.0.0.1:{self.server.server_port}",
                    f"http://localhost:{self.server.server_port}",
                }:
                    return self.send(403, {"error": "Invalid origin."})
                if not hmac.compare_digest(self.headers.get("X-CRM-CSRF", ""), csrf):
                    return self.send(
                        403,
                        {"error": "Reload the local dashboard before making changes."},
                    )
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                return self.send(415, {"error": "Use application/json."})
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 65536:
                    return self.send(413, {"error": "Request must be 1–65536 bytes."})
                data = json.loads(self.rfile.read(size))
                if not isinstance(data, dict):
                    raise CRMError("Expected a JSON object.")
                if hook:
                    result = receive_web3forms(store, data)
                elif path == "/api/accounts":
                    result = store.add_account(**data)
                elif path == "/api/contacts":
                    result = store.add_contact(**data)
                elif path == "/api/opportunities":
                    result = store.add_opportunity(**data)
                elif path == "/api/intake":
                    allowed = {"external_id", "subject", "sender", "body", "direction"}
                    if data.keys() - allowed:
                        raise CRMError("Unsupported note fields.")
                    result = store.ingest("claude_code", **data)
                elif path == "/api/propose":
                    result = store.propose(**data, actor="dashboard")
                elif path == "/api/apply":
                    result = store.apply(
                        data["id"], confirm=data.get("confirm") is True
                    )
                elif path == "/api/reject":
                    result = store.reject(data["id"])
                elif path == "/api/complete-task":
                    result = store.complete_task(data["id"])
                elif path == "/api/judge":
                    result = judge_proposal(store, data["id"])
                elif path == "/api/gmail-sync":
                    result = sync_gmail(
                        store,
                        query=data.get("query", "in:inbox newer_than:14d"),
                        limit=data.get("limit", 20),
                    )
                else:
                    return self.send(404, {"error": "Not found."})
                return self.send(200, result)
            except (CRMError, ValueError, KeyError, TypeError) as e:
                return self.send(400, {"error": str(e)})
            except Exception:
                return self.send(
                    500,
                    {
                        "error": "The request failed. No external action was triggered by this error."
                    },
                )

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def serve(store, port=4780):
    server = make_server(store, port)
    print(f"Founder CRM: http://127.0.0.1:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
