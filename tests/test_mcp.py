import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

from founder_crm.core import Store


@unittest.skipUnless(
    importlib.util.find_spec("mcp"), "Install the mcp extra to exercise stdio tools"
)
class MCPTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_stdio_tools_propose_but_cannot_approve(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "crm.db"
            store = Store(db)
            store.init()
            account = store.add_account("MCP Example", "prospect")["id"]
            params = StdioServerParameters(
                command=sys.executable,
                args=["-m", "founder_crm", "--db", str(db), "mcp"],
                env={**os.environ, "FOUNDER_CRM_ALLOW_MODEL_EGRESS": "0"},
            )
            async with stdio_client(params) as (reader, writer):
                async with ClientSession(reader, writer) as session:
                    await session.initialize()
                    names = {t.name for t in (await session.list_tools()).tools}
                    self.assertIn("crm_judge_update", names)
                    self.assertFalse(any("apply" in n or "approve" in n for n in names))
                    note = await session.call_tool(
                        "crm_intake_note",
                        {
                            "external_id": "call-stdio",
                            "subject": "Intro",
                            "body": "Please send two possible times.",
                        },
                    )
                    self.assertFalse(note.isError)
                    intake_id = json.loads(note.content[0].text)["id"]
                    proposal = await session.call_tool(
                        "crm_propose_update",
                        {
                            "intake_id": intake_id,
                            "action": "create_task",
                            "payload": {
                                "account_id": account,
                                "title": "Offer two times",
                            },
                        },
                    )
                    self.assertFalse(proposal.isError)
                    p = json.loads(proposal.content[0].text)
                    self.assertEqual(p["status"], "pending")
                    self.assertEqual(store.dashboard()["tasks"], [])
                    judgment = await session.call_tool(
                        "crm_judge_update", {"proposal_id": p["id"]}
                    )
                    self.assertTrue(judgment.isError)
                    self.assertEqual(store.proposal(p["id"])["status"], "pending")
                    self.assertFalse(
                        (await session.read_resource("crm://operating-rules")).contents
                        == []
                    )


if __name__ == "__main__":
    unittest.main()
