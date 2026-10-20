import base64
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from loop_crm.core import Store, CRMError
from loop_crm.demo import seed_demo
from loop_crm.integrations import receive_web3forms, sync_gmail
from loop_crm.judge import judge_proposal


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name) / "crm.db")
        self.store.init()
        self.account = self.store.add_account("Example Studio", "customer")["id"]
        self.store.add_contact(self.account, "Example Person", "person@studio.example")
        self.note = self.store.ingest(
            "claude_code",
            "call-1",
            "Call note",
            "person@studio.example",
            "Please follow up with two possible demo times.",
            "internal",
        )["id"]

    def proposal(self, action="create_task", payload=None, intake=None):
        return self.store.propose(
            intake or self.note,
            action,
            payload or {"account_id": self.account, "title": "Offer two times"},
        )["id"]

    def fixed_ticket(self):
        self.store.apply(
            self.proposal(
                "open_ticket", {"account_id": self.account, "title": "Export failed"}
            ),
            confirm=True,
        )
        tid = self.store.dashboard()["tickets"][0]["id"]
        self.store.apply(self.proposal("record_fix", {"ticket_id": tid}), confirm=True)
        return tid

    def test_import_retries_keep_original_evidence(self):
        r = self.store.ingest("claude_code", "call-1", "Different", "", "Changed")
        self.assertEqual(r, {"id": self.note, "duplicate": True})
        self.assertIn(
            "demo times", self.store.context(self.note)["source_evidence"]["body"]
        )

    def test_exact_contact_matching_and_unknown_sender(self):
        r = self.store.ingest(
            "gmail", "g-1", "Hi", "PERSON@STUDIO.EXAMPLE", "Hello", trusted=True
        )
        self.assertEqual(
            self.store.context(r["id"])["known_account"]["id"], self.account
        )
        r = self.store.ingest(
            "gmail", "g-2", "Hi", "other@studio.example", "Hello", trusted=True
        )
        self.assertIsNone(self.store.context(r["id"])["known_account"])

    def test_proposal_does_not_apply(self):
        p = self.proposal()
        self.assertEqual(self.store.proposal(p)["status"], "pending")
        self.assertEqual(self.store.dashboard()["tasks"], [])

    def test_human_confirmation_required(self):
        p = self.proposal()
        for kwargs in ({}, {"confirm": True, "actor": "claude_code"}):
            with self.assertRaises(CRMError):
                self.store.apply(p, **kwargs)
        self.assertEqual(self.store.proposal(p)["status"], "pending")

    def test_apply_once_and_audit(self):
        p = self.proposal()
        self.store.apply(p, confirm=True)
        with self.assertRaises(CRMError):
            self.store.apply(p, confirm=True)
        self.assertEqual(len(self.store.dashboard()["tasks"]), 1)
        audit = self.store.dashboard()["audit"][0]
        self.assertEqual(audit["actor"], "human")
        self.assertTrue(json.loads(audit["detail"])["human_review"])

    def test_rejected_proposal_cannot_apply(self):
        p = self.proposal()
        self.store.reject(p)
        with self.assertRaises(CRMError):
            self.store.apply(p, confirm=True)

    def test_non_buyers_cannot_enter_sales_pipeline(self):
        for relationship in ("investor", "vendor", "partner", "unknown"):
            a = self.store.add_account(relationship, relationship)["id"]
            with self.assertRaises(CRMError):
                self.store.add_opportunity(a, "Demo")

    def test_open_pipeline_blocks_nonbuyer_reclassification(self):
        self.store.add_opportunity(self.account, "Trial")
        p = self.proposal(
            "set_relationship", {"account_id": self.account, "relationship": "vendor"}
        )
        with self.assertRaises(CRMError):
            self.store.apply(p, confirm=True)
        self.assertEqual(self.store.proposal(p)["status"], "pending")

    def test_unknown_and_invalid_dates_are_not_invented(self):
        p = self.proposal()
        self.store.apply(p, confirm=True)
        self.assertIsNone(self.store.dashboard()["tasks"][0]["due_date"])
        with self.assertRaises(CRMError):
            self.proposal(
                payload={
                    "account_id": self.account,
                    "title": "Follow up",
                    "due_date": "next week",
                }
            )

    def test_payload_unknown_fields_and_missing_targets_rejected(self):
        for payload in (
            {"account_id": self.account, "title": "Next", "paid": True},
            {"account_id": 9999, "title": "Next"},
            {"account_id": True, "title": "Next"},
        ):
            with self.assertRaises(CRMError):
                self.proposal(payload=payload)

    def test_tampered_proposal_fails_without_write(self):
        p = self.proposal()
        with self.store.connection(True) as c:
            c.execute(
                "UPDATE proposals SET payload=? WHERE id=?",
                (json.dumps({"account_id": self.account, "title": "Tampered"}), p),
            )
        with self.assertRaises(CRMError):
            self.store.apply(p, confirm=True)
        self.assertEqual(self.store.dashboard()["tasks"], [])

    def test_source_changes_require_new_proposal(self):
        p = self.proposal()
        with self.store.connection(True) as c:
            c.execute("UPDATE intake SET body=? WHERE id=?", ("Edited", self.note))
        with self.assertRaises(CRMError):
            self.store.apply(p, confirm=True)

    def test_relationship_changes_require_new_proposal(self):
        p = self.proposal()
        with self.store.connection(True) as c:
            c.execute(
                "UPDATE accounts SET lifecycle='active' WHERE id=?", (self.account,)
            )
        with self.assertRaises(CRMError):
            self.store.apply(p, confirm=True)

    def test_judge_context_contains_target_ticket_and_stale_target_blocks_apply(self):
        tid = self.fixed_ticket()
        p = self.proposal("record_notification", {"ticket_id": tid})
        context = self.store.proposal(p)["context"]
        self.assertEqual(context["target_record"]["record"]["status"], "fixed")
        self.assertEqual(context["target_account"]["id"], self.account)
        with self.store.connection(True) as c:
            c.execute("UPDATE tickets SET title=? WHERE id=?", ("Changed issue", tid))
        with self.assertRaisesRegex(CRMError, "target record changed"):
            self.store.apply(p, confirm=True)

    def test_fixed_is_not_notified(self):
        tid = self.fixed_ticket()
        self.assertIsNone(self.store.dashboard()["tickets"][0]["notified_at"])
        p = self.proposal("record_notification", {"ticket_id": tid})
        with self.assertRaisesRegex(CRMError, "sent message"):
            self.store.apply(p, confirm=True)
        self.assertEqual(self.store.proposal(p)["status"], "pending")

    def test_sent_evidence_must_match_ticket_account(self):
        tid = self.fixed_ticket()
        other = self.store.add_account("Other", "customer")["id"]
        self.store.add_contact(other, "Other", "other@other.example")
        i = self.store.ingest(
            "gmail",
            "sent-other",
            "Fix",
            "other@other.example",
            "Export fixed",
            "out",
            trusted=True,
        )["id"]
        p = self.proposal("record_notification", {"ticket_id": tid}, i)
        with self.assertRaisesRegex(CRMError, "match a contact"):
            self.store.apply(p, confirm=True)

    def test_sent_evidence_allows_human_to_record_notification(self):
        tid = self.fixed_ticket()
        i = self.store.ingest(
            "gmail",
            "sent-1",
            "Fix",
            "person@studio.example",
            "Your export is fixed.",
            "out",
            trusted=True,
        )["id"]
        self.store.apply(
            self.proposal("record_notification", {"ticket_id": tid}, i), confirm=True
        )
        self.assertIsNotNone(self.store.dashboard()["tickets"][0]["notified_at"])

    def test_non_gmail_cannot_attest_provider_origin(self):
        with self.assertRaises(CRMError):
            self.store.ingest(
                "claude_code", "forged", "Sent", "", "Told them", "out", trusted=True
            )

    def test_contact_email_unique_case_insensitive(self):
        with self.assertRaises(CRMError):
            self.store.add_contact(self.account, "Duplicate", "PERSON@STUDIO.EXAMPLE")

    def test_web3forms_deduplicates_and_strips_credentials(self):
        payload = {
            "email": "person@studio.example",
            "message": "Can we try a demo?",
            "access_key": "never-retain",
            "token": "private",
        }
        first = receive_web3forms(self.store, payload)
        again = receive_web3forms(self.store, {**payload, "access_key": "rotated"})
        self.assertEqual(first["id"], again["id"])
        body = self.store.context(first["id"])["source_evidence"]["body"]
        self.assertNotIn("access_key", body)
        self.assertNotIn("private", body)
        self.assertEqual(
            self.store.context(first["id"])["source_evidence"]["trusted"], 0
        )

    def test_bad_web3forms_payload_rejected(self):
        for payload in ([], {"email": "x", "message": "Hi"}, {"email": "x@x.example"}):
            with self.assertRaises(CRMError):
                receive_web3forms(self.store, payload)

    def test_gmail_nested_text_direction_and_deduplication(self):
        paths = []
        text = base64.urlsafe_b64encode(b"Your export is fixed.").decode().rstrip("=")
        msg = {
            "labelIds": ["SENT"],
            "payload": {
                "mimeType": "multipart/mixed",
                "headers": [
                    {"name": "To", "value": "Example <person@studio.example>"},
                    {"name": "Subject", "value": "Fix"},
                ],
                "parts": [
                    {"mimeType": "text/plain", "body": {"data": text}},
                    {
                        "mimeType": "application/pdf",
                        "body": {"attachmentId": "never-download"},
                    },
                ],
            },
        }

        def fetch(path):
            paths.append(path)
            return (
                {"messages": [{"id": "abc"}], "nextPageToken": "more"}
                if path.startswith("messages?")
                else msg
            )

        self.assertTrue(sync_gmail(self.store, fetch=fetch)["has_more"])
        self.assertEqual(sync_gmail(self.store, fetch=fetch)["duplicates"], 1)
        item = self.store.dashboard()["intake"][0]
        self.assertEqual(
            (item["direction"], item["trusted"], item["body"]),
            ("out", 1, "Your export is fixed."),
        )
        self.assertNotIn("attachments", "".join(paths))

    def test_multi_recipient_gmail_cannot_match_single_contact(self):
        msg = {
            "labelIds": ["SENT"],
            "snippet": "Hi",
            "payload": {
                "headers": [
                    {
                        "name": "To",
                        "value": "person@studio.example, other@other.example",
                    }
                ]
            },
        }
        sync_gmail(
            self.store,
            fetch=lambda path: (
                {"messages": [{"id": "multi"}]} if path.startswith("messages?") else msg
            ),
        )
        item = self.store.dashboard()["intake"][0]
        self.assertEqual(item["sender"], "")
        self.assertIsNone(item["contact_id"])

    def test_gmail_limit_rejected_before_network(self):
        with self.assertRaises(CRMError):
            sync_gmail(
                self.store, limit=51, fetch=lambda _: self.fail("network called")
            )

    def test_model_sharing_is_off_by_default(self):
        p = self.proposal()
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("loop_crm.judge.urlopen") as network,
        ):
            with self.assertRaisesRegex(CRMError, "sharing is off"):
                judge_proposal(self.store, p)
            network.assert_not_called()

    @staticmethod
    def valid_response():
        return {
            "model": "jev-fixture",
            "answers": {
                "supported": {
                    "type": "choice",
                    "choice": "SUPPORTED",
                    "probabilities": {
                        "SUPPORTED": 0.8,
                        "UNSUPPORTED": 0.1,
                        "INSUFFICIENT": 0.1,
                    },
                    "confidence": 0.4,
                }
            },
        }

    def test_valid_judge_fixture_remains_pending_with_unknown_cost(self):
        p = self.proposal()
        sent = []

        def transport(payload):
            sent.append(payload)
            return self.valid_response()

        with patch.dict(os.environ, {}, clear=True):
            result = judge_proposal(self.store, p, transport=transport)
        self.assertFalse(result["applied"])
        self.assertIsNone(result["cost_usd"])
        self.assertEqual(self.store.proposal(p)["status"], "pending")
        self.assertEqual(self.store.dashboard()["tasks"], [])
        self.assertEqual(
            sent[0]["state"]["evidence"]["known_account"]["relationship"], "customer"
        )

    def test_malformed_judgment_never_applies(self):
        p = self.proposal()
        wrong = self.valid_response()
        wrong["answers"]["supported"]["confidence"] = float("nan")
        for response in (
            {},
            wrong,
            {**self.valid_response(), "model": "another-model"},
        ):
            with self.assertRaises(CRMError):
                judge_proposal(self.store, p, transport=lambda _, r=response: r)
        self.assertEqual(self.store.proposal(p)["status"], "pending")
        self.assertEqual(self.store.proposal(p)["judgments"], [])

    def test_inconsistent_choice_or_usage_is_not_recorded(self):
        p = self.proposal()
        wrong_choice = self.valid_response()
        wrong_choice["answers"]["supported"]["choice"] = "UNSUPPORTED"
        wrong_cost = {**self.valid_response(), "usage": {"cost": -1}}
        for response in (wrong_choice, wrong_cost):
            with self.assertRaises(CRMError):
                judge_proposal(self.store, p, transport=lambda _, r=response: r)
        self.assertEqual(self.store.proposal(p)["judgments"], [])

    def test_provider_failure_leaves_proposal_pending(self):
        p = self.proposal()
        with (
            patch.dict(
                os.environ,
                {
                    "LOOP_CRM_ALLOW_MODEL_EGRESS": "1",
                    "LOOP_CRM_JEV_API_KEY": "synthetic-test-key",
                    "LOOP_CRM_JEV_PROVIDER": "typesafe",
                },
            ),
            patch("loop_crm.judge.urlopen", side_effect=TimeoutError),
        ):
            with self.assertRaisesRegex(CRMError, "unavailable"):
                judge_proposal(self.store, p)
        self.assertEqual(self.store.proposal(p)["status"], "pending")
        self.assertEqual(self.store.proposal(p)["judgments"], [])

    def test_demo_is_explicit_fiction_and_has_no_judgments(self):
        s = Store(Path(self.tmp.name) / "demo.db")
        seed_demo(s)
        self.assertEqual(s.dashboard()["counts"]["accounts"], 4)
        with s.connection() as c:
            self.assertEqual(
                c.execute("SELECT count(*) FROM judgments").fetchone()[0], 0
            )
            self.assertTrue(
                all(
                    r[0].endswith(".example")
                    for r in c.execute("SELECT email FROM contacts")
                )
            )
        with self.assertRaises(CRMError):
            seed_demo(s)


if __name__ == "__main__":
    unittest.main()
