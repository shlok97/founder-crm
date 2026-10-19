from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import sqlite3
from datetime import date
from pathlib import Path

RELATIONSHIPS = {
    "prospect",
    "customer",
    "investor",
    "partner",
    "adviser",
    "vendor",
    "other",
    "unknown",
}
LIFECYCLES = {"new", "engaged", "pilot", "active", "dormant", "closed"}
STAGES = {"discovery", "demo", "pilot", "proposal", "won", "lost"}
ACTIONS = {
    "log_interaction",
    "create_task",
    "open_ticket",
    "record_fix",
    "record_notification",
    "set_relationship",
    "set_stage",
}


class CRMError(ValueError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def clean_text(value, field, maximum=20000, required=True):
    if (
        not isinstance(value, str)
        or len(value) > maximum
        or (required and not value.strip())
    ):
        raise CRMError(
            f"{field} must be text, 1–{maximum} characters."
            if required
            else f"Invalid {field}."
        )
    return value.strip()


def integer(value, field):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise CRMError(f"{field} must be a positive integer.")
    return value


class Store:
    def __init__(self, path=None):
        self.path = Path(path or os.getenv("FOUNDER_CRM_DB", "data/crm.db")).resolve()

    @contextlib.contextmanager
    def connection(self, write=False):
        if not self.path.exists():
            raise CRMError(
                "Database not initialized. Run python -m founder_crm init first."
            )
        c = sqlite3.connect(self.path, timeout=15)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys=ON")
        try:
            if write:
                c.execute("BEGIN IMMEDIATE")
            else:
                c.execute("PRAGMA query_only=ON")
            yield c
            if write:
                c.commit()
        except Exception:
            c.rollback()
            raise
        finally:
            c.close()

    def init(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as c:
            c.executescript(Path(__file__).with_name("schema.sql").read_text())
        self.path.chmod(0o600)
        return {"database": str(self.path), "schema_version": 1}

    @staticmethod
    def audit(c, actor, action, kind, id, detail):
        c.execute(
            "INSERT INTO audit(actor,action,object_type,object_id,detail) VALUES(?,?,?,?,?)",
            (actor, action, kind, id, canonical(detail)),
        )

    @staticmethod
    def one(c, table, id):
        if table not in {
            "accounts",
            "contacts",
            "intake",
            "proposals",
            "tickets",
            "opportunities",
            "tasks",
        }:
            raise CRMError("Invalid table.")
        row = c.execute(
            f"SELECT * FROM {table} WHERE id=?", (integer(id, "id"),)
        ).fetchone()
        if row is None:
            raise CRMError(f"{table} record not found.")
        return dict(row)

    def add_account(self, name, relationship="unknown", lifecycle="new", actor="human"):
        name = clean_text(name, "name", 200)
        if relationship not in RELATIONSHIPS or lifecycle not in LIFECYCLES:
            raise CRMError("Invalid relationship or lifecycle.")
        with self.connection(True) as c:
            id = c.execute(
                "INSERT INTO accounts(name,relationship,lifecycle) VALUES(?,?,?)",
                (name, relationship, lifecycle),
            ).lastrowid
            self.audit(c, actor, "created", "account", id, {"name": name})
        return {"id": id}

    def add_contact(self, account_id, name, email=None, actor="human"):
        name = clean_text(name, "name", 200)
        if email:
            email = clean_text(email, "email", 254).lower()
            if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
                raise CRMError("Enter a valid email address.")
        with self.connection(True) as c:
            self.one(c, "accounts", account_id)
            try:
                id = c.execute(
                    "INSERT INTO contacts(account_id,name,email) VALUES(?,?,?)",
                    (account_id, name, email or None),
                ).lastrowid
            except sqlite3.IntegrityError as e:
                raise CRMError("A contact already uses that email.") from e
            self.audit(c, actor, "created", "contact", id, {"account_id": account_id})
        return {"id": id}

    def add_opportunity(self, account_id, title, stage="discovery"):
        title = clean_text(title, "title", 300)
        if stage not in STAGES:
            raise CRMError("Invalid pipeline stage.")
        with self.connection(True) as c:
            account = self.one(c, "accounts", account_id)
            if account["relationship"] not in {"prospect", "customer"}:
                raise CRMError(
                    "Only prospects and customers belong in the sales pipeline."
                )
            id = c.execute(
                "INSERT INTO opportunities(account_id,title,stage) VALUES(?,?,?)",
                (account_id, title, stage),
            ).lastrowid
            self.audit(
                c, "human", "created", "opportunity", id, {"account_id": account_id}
            )
        return {"id": id}

    def ingest(
        self,
        source,
        external_id,
        subject,
        sender,
        body,
        direction="in",
        *,
        trusted=False,
    ):
        if source not in {"gmail", "web3forms", "claude_code", "demo", "import"}:
            raise CRMError("Unknown input channel.")
        if direction not in {"in", "out", "internal"}:
            raise CRMError("Invalid direction.")
        subject = clean_text(subject, "subject", 500)
        body = clean_text(body, "body")
        external_id = clean_text(external_id, "external_id", 300)
        sender = clean_text(sender, "sender", 254, False).lower()
        if trusted and source != "gmail":
            raise CRMError(
                "Only the Gmail pull adapter can attest to provider-origin evidence."
            )
        with self.connection(True) as c:
            prior = c.execute(
                "SELECT id FROM intake WHERE source=? AND external_id=?",
                (source, external_id),
            ).fetchone()
            if prior:
                return {"id": prior["id"], "duplicate": True}
            contact = c.execute(
                "SELECT id FROM contacts WHERE email=? COLLATE NOCASE", (sender,)
            ).fetchone()
            id = c.execute(
                "INSERT INTO intake(source,external_id,subject,sender,body,direction,trusted,contact_id) VALUES(?,?,?,?,?,?,?,?)",
                (
                    source,
                    external_id,
                    subject,
                    sender,
                    body,
                    direction,
                    int(trusted),
                    contact["id"] if contact else None,
                ),
            ).lastrowid
            self.audit(c, source, "received", "intake", id, {"source": source})
        return {"id": id, "duplicate": False}

    def context(self, id):
        with self.connection() as c:
            item = self.one(c, "intake", id)
            context = {
                "source_evidence": item,
                "known_account": None,
                "recent_interactions": [],
            }
            if item["contact_id"]:
                contact = self.one(c, "contacts", item["contact_id"])
                context["known_account"] = self.one(
                    c, "accounts", contact["account_id"]
                )
                context["recent_interactions"] = [
                    dict(r)
                    for r in c.execute(
                        "SELECT summary,direction,created_at FROM interactions WHERE account_id=? ORDER BY id DESC LIMIT 5",
                        (contact["account_id"],),
                    )
                ]
        return context

    def validate_payload(self, action, payload):
        if action not in ACTIONS or not isinstance(payload, dict):
            raise CRMError("Unknown action or invalid payload.")
        required = {
            "log_interaction": {"account_id", "summary"},
            "create_task": {"account_id", "title"},
            "open_ticket": {"account_id", "title"},
            "record_fix": {"ticket_id"},
            "record_notification": {"ticket_id"},
            "set_relationship": {"account_id", "relationship"},
            "set_stage": {"opportunity_id", "stage"},
        }[action]
        optional = {"create_task": {"due_date"}}.get(action, set())
        if not required <= payload.keys() or payload.keys() - required - optional:
            raise CRMError(
                f"{action} requires {sorted(required)}; optional: {sorted(optional)}."
            )
        for k in required:
            if k.endswith("_id"):
                integer(payload[k], k)
        for k in ("title", "summary"):
            if k in payload:
                clean_text(payload[k], k, 2000)
        if "relationship" in payload and payload["relationship"] not in RELATIONSHIPS:
            raise CRMError("Invalid relationship.")
        if "stage" in payload and payload["stage"] not in STAGES:
            raise CRMError("Invalid stage.")
        if payload.get("due_date"):
            try:
                date.fromisoformat(payload["due_date"])
            except (ValueError, TypeError) as e:
                raise CRMError("due_date must be YYYY-MM-DD.") from e
        return payload

    def propose(self, intake_id, action, payload, actor="claude_code"):
        self.validate_payload(action, payload)
        context = self.context(intake_id)
        with self.connection(True) as c:
            for key, table in [
                ("account_id", "accounts"),
                ("ticket_id", "tickets"),
                ("opportunity_id", "opportunities"),
            ]:
                if key in payload:
                    target = self.one(c, table, payload[key])
                    context["target_record"] = {"table": table, "record": target}
                    context["target_account"] = (
                        target
                        if table == "accounts"
                        else self.one(c, "accounts", target["account_id"])
                    )
            # Freeze the evidence and known relationship actually shown to the judge.
            fingerprint = digest(
                {"context": context, "action": action, "payload": payload}
            )
            id = c.execute(
                "INSERT INTO proposals(intake_id,action,payload,context,evidence_hash,created_by) VALUES(?,?,?,?,?,?)",
                (
                    intake_id,
                    action,
                    canonical(payload),
                    canonical(context),
                    fingerprint,
                    actor,
                ),
            ).lastrowid
            self.audit(c, actor, "proposed", "proposal", id, {"action": action})
        return {"id": id, "status": "pending", "evidence_hash": fingerprint}

    def proposal(self, id):
        with self.connection() as c:
            p = self.one(c, "proposals", id)
            p["payload"] = json.loads(p["payload"])
            p["context"] = json.loads(p["context"])
            p["judgments"] = [
                dict(r)
                for r in c.execute(
                    "SELECT * FROM judgments WHERE proposal_id=? ORDER BY id DESC",
                    (id,),
                )
            ]
        return p

    def apply(self, id, *, confirm=False, actor="human"):
        if not confirm or actor != "human":
            raise CRMError(
                "A person must explicitly approve this update in the dashboard or CLI."
            )
        with self.connection(True) as c:
            p = self.one(c, "proposals", id)
            if p["status"] != "pending":
                raise CRMError("This proposal has already been resolved.")
            data = json.loads(p["payload"])
            action = p["action"]
            self.validate_payload(action, data)
            context = json.loads(p["context"])
            if (
                digest({"context": context, "action": action, "payload": data})
                != p["evidence_hash"]
            ):
                raise CRMError(
                    "Proposal evidence was changed. Create a fresh proposal."
                )
            source = self.one(c, "intake", p["intake_id"])
            if source != context["source_evidence"]:
                raise CRMError("Source evidence changed. Create a fresh proposal.")
            known = context.get("known_account")
            if known and self.one(c, "accounts", known["id"]) != known:
                raise CRMError("Relationship context changed. Create a fresh proposal.")
            target = context.get("target_record")
            if (
                target
                and self.one(c, target["table"], target["record"]["id"])
                != target["record"]
            ):
                raise CRMError("The target record changed. Create a fresh proposal.")
            target_account = context.get("target_account")
            if (
                target_account
                and self.one(c, "accounts", target_account["id"]) != target_account
            ):
                raise CRMError(
                    "The target relationship changed. Create a fresh proposal."
                )
            if action == "log_interaction":
                c.execute(
                    "INSERT INTO interactions(account_id,intake_id,proposal_id,summary,direction) VALUES(?,?,?,?,?)",
                    (
                        data["account_id"],
                        p["intake_id"],
                        id,
                        data["summary"],
                        source["direction"],
                    ),
                )
            elif action == "create_task":
                c.execute(
                    "INSERT INTO tasks(account_id,title,due_date,proposal_id) VALUES(?,?,?,?)",
                    (
                        data["account_id"],
                        data["title"],
                        data.get("due_date") or None,
                        id,
                    ),
                )
            elif action == "open_ticket":
                c.execute(
                    "INSERT INTO tickets(account_id,title,proposal_id) VALUES(?,?,?)",
                    (data["account_id"], data["title"], id),
                )
            elif action == "record_fix":
                self.one(c, "tickets", data["ticket_id"])
                c.execute(
                    "UPDATE tickets SET status='fixed',fixed_at=CURRENT_TIMESTAMP WHERE id=?",
                    (data["ticket_id"],),
                )
            elif action == "record_notification":
                ticket = self.one(c, "tickets", data["ticket_id"])
                if not ticket["fixed_at"]:
                    raise CRMError("Record the fix before its notification.")
                if not (
                    source["source"] == "gmail"
                    and source["trusted"]
                    and source["direction"] == "out"
                ):
                    raise CRMError(
                        "A notification requires a sent message verified by the Gmail pull adapter; an internal note is not delivery evidence."
                    )
                contact = (
                    self.one(c, "contacts", source["contact_id"])
                    if source["contact_id"]
                    else None
                )
                if not contact or contact["account_id"] != ticket["account_id"]:
                    raise CRMError(
                        "The sent message must match a contact on this ticket account."
                    )
                c.execute(
                    "UPDATE tickets SET notified_at=CURRENT_TIMESTAMP WHERE id=?",
                    (data["ticket_id"],),
                )
            elif action == "set_relationship":
                if (
                    data["relationship"] not in {"customer", "prospect"}
                    and c.execute(
                        "SELECT 1 FROM opportunities WHERE account_id=? AND stage NOT IN ('lost','won')",
                        (data["account_id"],),
                    ).fetchone()
                ):
                    raise CRMError(
                        "Resolve open sales opportunities before changing this account to a non-buyer relationship."
                    )
                c.execute(
                    "UPDATE accounts SET relationship=? WHERE id=?",
                    (data["relationship"], data["account_id"]),
                )
            elif action == "set_stage":
                opp = self.one(c, "opportunities", data["opportunity_id"])
                account = self.one(c, "accounts", opp["account_id"])
                if account["relationship"] not in {"prospect", "customer"}:
                    raise CRMError(
                        "Investors and other non-buyers do not enter the customer pipeline."
                    )
                c.execute(
                    "UPDATE opportunities SET stage=? WHERE id=?",
                    (data["stage"], data["opportunity_id"]),
                )
            c.execute("UPDATE proposals SET status='applied' WHERE id=?", (id,))
            self.audit(
                c,
                actor,
                "applied",
                "proposal",
                id,
                {"action": action, "human_review": True},
            )
        return {"id": id, "status": "applied"}

    def reject(self, id):
        with self.connection(True) as c:
            p = self.one(c, "proposals", id)
            if p["status"] != "pending":
                raise CRMError("Proposal already resolved.")
            c.execute("UPDATE proposals SET status='rejected' WHERE id=?", (id,))
            self.audit(c, "human", "rejected", "proposal", id, {})
        return {"id": id, "status": "rejected"}

    def complete_task(self, id):
        with self.connection(True) as c:
            self.one(c, "tasks", id)
            c.execute("UPDATE tasks SET status='done' WHERE id=?", (id,))
            self.audit(c, "human", "completed", "task", id, {})
        return {"id": id, "status": "done"}

    def dashboard(self):
        with self.connection() as c:
            counts = {
                t: c.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
                for t in ["accounts", "contacts", "interactions", "intake"]
            }
            accounts = [
                dict(r)
                for r in c.execute(
                    "SELECT a.*,count(c.id) AS contact_count FROM accounts a LEFT JOIN contacts c ON c.account_id=a.id GROUP BY a.id ORDER BY a.id DESC"
                )
            ]
            proposals = [
                dict(r)
                for r in c.execute(
                    "SELECT p.*,i.subject,i.source,j.verdict,j.confidence FROM proposals p JOIN intake i ON i.id=p.intake_id LEFT JOIN judgments j ON j.id=(SELECT max(j2.id) FROM judgments j2 WHERE j2.proposal_id=p.id) WHERE p.status='pending' ORDER BY p.id DESC"
                )
            ]
            tasks = [
                dict(r)
                for r in c.execute(
                    "SELECT t.*,a.name AS account_name FROM tasks t JOIN accounts a ON a.id=t.account_id WHERE t.status='open' ORDER BY t.due_date IS NULL,t.due_date,t.id"
                )
            ]
            tickets = [
                dict(r)
                for r in c.execute(
                    "SELECT t.*,a.name AS account_name FROM tickets t JOIN accounts a ON a.id=t.account_id ORDER BY t.id DESC"
                )
            ]
            intake = [
                dict(r)
                for r in c.execute(
                    "SELECT i.*,c.name AS contact_name FROM intake i LEFT JOIN contacts c ON c.id=i.contact_id ORDER BY i.id DESC LIMIT 100"
                )
            ]
            opportunities = [
                dict(r)
                for r in c.execute(
                    "SELECT o.*,a.name AS account_name FROM opportunities o JOIN accounts a ON a.id=o.account_id ORDER BY o.id DESC"
                )
            ]
            audit = [
                dict(r)
                for r in c.execute("SELECT * FROM audit ORDER BY id DESC LIMIT 30")
            ]
        return dict(
            counts=counts,
            accounts=accounts,
            proposals=proposals,
            tasks=tasks,
            tickets=tickets,
            intake=intake,
            opportunities=opportunities,
            audit=audit,
        )

    def account_history(self, id):
        with self.connection() as c:
            account = self.one(c, "accounts", id)
            account["contacts"] = [
                dict(r)
                for r in c.execute("SELECT * FROM contacts WHERE account_id=?", (id,))
            ]
            account["interactions"] = [
                dict(r)
                for r in c.execute(
                    "SELECT * FROM interactions WHERE account_id=? ORDER BY id DESC",
                    (id,),
                )
            ]
            account["tasks"] = [
                dict(r)
                for r in c.execute("SELECT * FROM tasks WHERE account_id=?", (id,))
            ]
            account["tickets"] = [
                dict(r)
                for r in c.execute("SELECT * FROM tickets WHERE account_id=?", (id,))
            ]
        return account
