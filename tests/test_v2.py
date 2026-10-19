"""Schema v2: upgrade, ticket loop, qualification, custom fields, follow-ups."""

import sqlite3
import tempfile
import unittest
from pathlib import Path

from founder_crm.core import CRMError, Store

V1_SCHEMA = """
CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
INSERT INTO meta VALUES('schema_version','1');
CREATE TABLE accounts(id INTEGER PRIMARY KEY,name TEXT NOT NULL,
 relationship TEXT NOT NULL DEFAULT 'unknown' CHECK(relationship IN ('prospect','customer','investor','partner','adviser','vendor','other','unknown')),
 lifecycle TEXT NOT NULL DEFAULT 'new' CHECK(lifecycle IN ('new','engaged','pilot','active','dormant','closed')),
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE contacts(id INTEGER PRIMARY KEY,account_id INTEGER NOT NULL REFERENCES accounts(id),
 name TEXT NOT NULL,email TEXT COLLATE NOCASE UNIQUE,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE tickets(id INTEGER PRIMARY KEY,account_id INTEGER NOT NULL REFERENCES accounts(id),title TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','fixed')),
 fixed_at TEXT,notified_at TEXT,proposal_id INTEGER UNIQUE,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
INSERT INTO accounts(name,relationship,lifecycle) VALUES('Old Studio','customer','active');
INSERT INTO contacts(account_id,name,email) VALUES(1,'Pat','pat@old.example');
INSERT INTO tickets(account_id,title,status,fixed_at) VALUES(1,'Export broke','fixed','2026-01-02 03:04:05');
"""


class V2Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "crm.db")
        self.store.init()
        self.account = self.store.add_account("Studio", "prospect", "pilot")["id"]

    def tearDown(self):
        self.tmp.cleanup()

    def test_v1_database_upgrades_without_losing_rows(self):
        path = Path(self.tmp.name) / "old.db"
        with sqlite3.connect(path) as c:
            c.executescript(V1_SCHEMA)
        store = Store(path)
        result = store.init()
        self.assertEqual(result["schema_version"], 2)
        self.assertTrue(Path(result["backup"]).exists())
        ticket = store.dashboard()["tickets"][0]
        self.assertEqual(
            (ticket["title"], ticket["status"], ticket["fixed_at"], ticket["kind"]),
            ("Export broke", "fixed", "2026-01-02 03:04:05", "bug"),
        )
        self.assertEqual(store.untold()[0]["id"], ticket["id"])
        self.assertNotIn("backup", store.init())  # second run is a no-op
        with sqlite3.connect(path) as c:
            self.assertEqual(c.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_ticket_loop_keeps_fixed_closed_and_told_apart(self):
        t = self.store.open_ticket(
            self.account, "Export 504", kind="bug", severity="high",
            reported_via="whatsapp", body="it just spins",
            next_action="raise timeout", next_action_date="2026-10-25",
        )["id"]
        history = self.store.account_history(self.account)
        self.assertEqual(history["interactions"][0]["kind"], "feedback")
        self.assertEqual(self.store.followups()[0]["kind"], "ticket")
        with self.assertRaises(CRMError):
            self.store.notify_ticket(t, "whatsapp", "done")
        self.store.close_ticket(t, resolution="300s budget", release_ref="r1")
        self.assertEqual([x["id"] for x in self.store.untold()], [t])
        self.assertEqual(self.store.followups(), [])
        r = self.store.notify_ticket(t, "whatsapp", "Told Sam it works")
        self.assertFalse(r["verified"])
        self.assertEqual(self.store.untold(), [])
        ticket = self.store.ticket(t)
        self.assertEqual((ticket["notified_via"], ticket["notification_verified"]), ("whatsapp", 0))
        self.store.set_ticket_status(t, "in_progress")
        reopened = self.store.ticket(t)
        self.assertIsNone(reopened["notified_at"])
        self.assertIn("previous", reopened["history"][-1]["detail"])

    def test_ticket_contact_must_belong_to_account(self):
        other = self.store.add_account("Other", "customer")["id"]
        person = self.store.add_contact(other, "Lee", "lee@other.example")["id"]
        with self.assertRaises(CRMError):
            self.store.open_ticket(self.account, "Wrong", contact_id=person)

    def test_qualification_counts_custom_questions_and_keeps_unknown(self):
        self.store.define_field(
            "account", "plan_tier", "Plan tier", "choice", ["free", "team"], qualification=True
        )
        status = self.store.set_qualification(self.account, team_size=4, plan_tier="team")
        self.assertEqual((status["filled"], status["total"], status["status"]), (2, 9, "thin"))
        self.assertIn("fit_score", status["missing"])
        with self.assertRaises(CRMError):
            self.store.set_qualification(self.account, plan_tier="enterprise")
        with self.assertRaises(CRMError):
            self.store.set_qualification(self.account, fit_score=9)
        self.store.add_evidence(self.account, "4 analysts", "call 2026-10-01")
        q = self.store.qualification(self.account)
        self.assertEqual(len(q["evidence"]), 1)
        gaps = self.store.qualification_gaps()
        self.assertEqual(gaps[0]["id"], self.account)
        investor = self.store.add_account("Fund", "investor")["id"]
        self.assertNotIn(investor, [g["id"] for g in self.store.qualification_gaps()])

    def test_custom_fields_validate_and_route(self):
        with self.assertRaises(CRMError):
            self.store.set_custom("account", self.account, "undefined", "x")
        with self.assertRaises(CRMError):
            self.store.define_field("account", "Bad Key", "Bad")
        with self.assertRaises(CRMError):
            self.store.define_field("account", "segment", "Segment")
        self.store.define_field("account", "seats_wanted", "Seats wanted", "integer")
        self.store.update_record("account", self.account, segment="agency", seats_wanted="12")
        history = self.store.account_history(self.account)
        self.assertEqual((history["segment"], history["custom"]["seats_wanted"]), ("agency", 12))
        with self.assertRaises(CRMError):
            self.store.update_record("account", self.account, seats_wanted="lots")
        with self.assertRaises(CRMError):
            self.store.define_field("account", "seats_wanted", "Seats", "text")
        self.store.update_record("account", self.account, seats_wanted=None)
        self.assertEqual(self.store.account_history(self.account)["custom"], {})

    def test_find_account_and_relationship_guard(self):
        self.assertEqual(self.store.find_account("stud")["id"], self.account)
        self.store.add_account("Studio North", "prospect")
        with self.assertRaises(CRMError):
            self.store.find_account("stud")
        self.store.add_opportunity(self.account, "Team plan", "negotiation", value=1200, currency="USD")
        with self.assertRaises(CRMError):
            self.store.update_account(self.account, relationship="investor")
        opp = self.store.account_history(self.account)["opportunities"][0]
        self.store.update_opportunity(opp["id"], stage="parked")
        self.store.update_account(self.account, relationship="investor")

    def test_interaction_keeps_when_it_happened(self):
        self.store.log_interaction(
            self.account, "Walked the export", "call", "out",
            channel="call", occurred_at="2026-09-01",
        )
        i = self.store.account_history(self.account)["interactions"][0]
        self.assertEqual((i["occurred_at"], i["kind"], i["channel"]), ("2026-09-01", "call", "call"))
        with self.assertRaises(CRMError):
            self.store.log_interaction(self.account, "x", "telepathy")


if __name__ == "__main__":
    unittest.main()
