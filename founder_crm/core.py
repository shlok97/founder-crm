from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import sqlite3
from datetime import date, datetime, timezone
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
LIFECYCLES = {
    "new",
    "engaged",
    "qualified",
    "pilot",
    "active",
    "churned",
    "lost",
    "dormant",
    "not_a_fit",
    "internal",
    "closed",
}
STAGES = {
    "discovery",
    "qualified",
    "demo",
    "pilot",
    "proposal",
    "negotiation",
    "won",
    "lost",
    "parked",
}
SCHEMA_VERSION = 2
CHANNELS = {
    "whatsapp",
    "email",
    "call",
    "in_person",
    "video",
    "linkedin",
    "app",
    "chat",
    "sms",
    "internal",
    "other",
}
TICKET_STATUSES = {
    "open",
    "triaged",
    "in_progress",
    "waiting_on_client",
    "fixed",
    "closed",
    "wont_do",
    "duplicate",
}
TICKET_KINDS = {
    "bug",
    "data_defect",
    "feature_request",
    "question",
    "performance",
    "access",
    "billing",
    "onboarding",
    "other",
}
SEVERITIES = {"blocker", "high", "normal", "low"}
OPEN_TICKET = {"open", "triaged", "in_progress", "waiting_on_client"}
CLOSED_TICKET = {"closed", "wont_do", "duplicate"}
OBJECT_TABLES = {
    "account": "accounts",
    "contact": "contacts",
    "opportunity": "opportunities",
    "ticket": "tickets",
    "interaction": "interactions",
    "event": "events",
}
FIELD_TYPES = {"text", "number", "integer", "date", "boolean", "choice", "json"}
# The qualification questions every business can ask. Add your own as account
# custom fields with qualification=1; they count toward completeness too.
QUALIFICATION_CORE = [
    ("entity_type", "Legal entity"),
    ("team_size", "Team size"),
    ("current_tools", "Tools they use today"),
    ("pain_points", "Pain points"),
    ("use_case", "What they would use it for"),
    ("budget_authority", "Holds the budget"),
    ("decision_process", "How they decide"),
    ("fit_score", "Fit score (1-5)"),
]
EDITABLE = {
    "accounts": {
        "name",
        "slug",
        "lifecycle",
        "segment",
        "tier",
        "website",
        "city",
        "region",
        "country",
        "source_id",
        "source_detail",
        "referred_by",
        "owner",
        "tags",
        "notes",
        "first_touch_at",
        "last_touch_at",
        "next_action",
        "next_action_date",
    },
    "contacts": {
        "name",
        "email",
        "title",
        "seniority",
        "decision_role",
        "phone",
        "whatsapp",
        "linkedin_url",
        "city",
        "status",
        "source_id",
        "source_detail",
        "consent_basis",
        "is_primary",
        "tags",
        "notes",
    },
    "opportunities": {
        "title",
        "stage",
        "primary_contact_id",
        "product",
        "value",
        "currency",
        "billing",
        "seats",
        "probability",
        "opened_at",
        "expected_close",
        "closed_at",
        "outcome_reason",
        "owner",
        "source_id",
        "next_action",
        "next_action_date",
        "notes",
    },
    "interactions": {
        "contact_id",
        "opportunity_id",
        "channel",
        "occurred_at",
        "body",
        "outcome",
    },
    "tickets": {
        "title",
        "contact_id",
        "kind",
        "severity",
        "area",
        "reported_at",
        "reported_via",
        "body",
        "expected",
        "resolution",
        "evidence",
        "commit_ref",
        "release_ref",
        "owner",
        "next_action",
        "next_action_date",
        "tags",
    },
    "qualification": {
        "as_of",
        "entity_type",
        "team_size",
        "current_tools",
        "pain_points",
        "use_case",
        "buying_trigger",
        "decision_process",
        "decision_contact_id",
        "budget_authority",
        "budget_band",
        "fit_score",
        "fit_rationale",
        "risk_flags",
        "confidence",
        "verified_by",
        "verified_at",
        "notes",
    },
    "events": {
        "organizer",
        "start_date",
        "end_date",
        "city",
        "venue",
        "role",
        "cost",
        "currency",
        "notes",
    },
}
TICKET_SELECT = (
    "SELECT t.*,a.name AS account_name,a.lifecycle AS account_lifecycle,"
    "c.name AS contact_name FROM tickets t JOIN accounts a ON a.id=t.account_id"
    " LEFT JOIN contacts c ON c.id=t.contact_id"
)
TICKET_ORDER = (
    " ORDER BY CASE t.severity WHEN 'blocker' THEN 1 WHEN 'high' THEN 2 WHEN 'normal' THEN 3 ELSE 4 END,"
    " CASE a.lifecycle WHEN 'active' THEN 1 WHEN 'pilot' THEN 2 ELSE 3 END,"
    " COALESCE(t.reported_at,t.created_at)"
)
FOLLOWUPS_SQL = """
SELECT * FROM (
SELECT 'task' AS kind,t.id,t.account_id,a.name AS account_name,t.title AS what,
       NULL AS next_action,t.due_date AS due FROM tasks t JOIN accounts a ON a.id=t.account_id
 WHERE t.status='open'
UNION ALL
SELECT 'opportunity',o.id,o.account_id,a.name,o.title||' ('||o.stage||')',o.next_action,o.next_action_date
  FROM opportunities o JOIN accounts a ON a.id=o.account_id
 WHERE o.next_action_date IS NOT NULL AND o.stage NOT IN ('lost','parked')
UNION ALL
SELECT 'relationship',a.id,a.id,a.name,a.lifecycle,a.next_action,a.next_action_date FROM accounts a
 WHERE a.next_action_date IS NOT NULL AND a.lifecycle NOT IN ('lost','not_a_fit','internal','closed')
   AND NOT EXISTS (SELECT 1 FROM opportunities o WHERE o.account_id=a.id
                   AND o.next_action_date IS NOT NULL AND o.stage NOT IN ('lost','parked'))
UNION ALL
SELECT 'ticket',t.id,t.account_id,a.name,'#'||t.id||' '||t.title,t.next_action,t.next_action_date
  FROM tickets t JOIN accounts a ON a.id=t.account_id
 WHERE t.next_action_date IS NOT NULL AND t.status NOT IN ('closed','wont_do','duplicate')
) ORDER BY due IS NULL,due
"""


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def today():
    return date.today().isoformat()


def tags(value):
    if value is None:
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            value = [t for t in re.split(r"[,\s]+", value) if t]
    if not isinstance(value, list) or not all(isinstance(t, str) for t in value):
        raise CRMError("tags must be a list of words.")
    return value


def coerce(field, value):
    """Check a custom value against its definition and return the stored form."""
    kind, key = field["type"], field["key"]
    try:
        if kind == "number":
            return float(value)
        if kind == "integer":
            if isinstance(value, float) and not value.is_integer():
                raise ValueError
            return int(value)
        if kind == "boolean":
            if isinstance(value, bool):
                return value
            if str(value).lower() in {"1", "true", "yes"}:
                return True
            if str(value).lower() in {"0", "false", "no"}:
                return False
            raise ValueError
        if kind == "date":
            return iso_date(value, key)
        if kind == "choice":
            if value not in json.loads(field["choices"]):
                raise ValueError
            return value
        if kind == "json":
            return json.loads(value) if isinstance(value, str) else value
        return str(value)
    except (ValueError, TypeError, json.JSONDecodeError) as e:
        raise CRMError(f"{key} does not accept {value!r} ({kind}).") from e
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


def iso_date(value, field):
    if value in (None, ""):
        return None
    try:
        date.fromisoformat(str(value)[:10])
    except ValueError as e:
        raise CRMError(f"{field} must start with YYYY-MM-DD.") from e
    return str(value)


def slugify(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:80] or "record"


def table_columns(c, table):
    return [r[1] for r in c.execute(f"PRAGMA table_info({table})")]


def upgrade(c, schema, path):
    """Rebuild tables whose columns changed, keeping every row and column value.

    SQLite cannot add CHECK values or reorder columns in place, so each changed
    table is copied into its new definition. Nothing is dropped: an old column
    with no new home stops the upgrade. A backup is written first."""
    ref = sqlite3.connect(":memory:")
    ref.executescript(schema)
    wanted = {
        name: sql
        for name, sql in ref.execute(
            "SELECT name,sql FROM sqlite_master WHERE type='table'"
        )
    }
    changed = []
    for table in wanted:
        old = table_columns(c, table)
        if old and old != table_columns(ref, table):
            lost = set(old) - set(table_columns(ref, table))
            if lost:
                raise CRMError(
                    f"Upgrade would drop {table}.{', '.join(sorted(lost))}; stopping."
                )
            changed.append(table)
    ref.close()
    if not changed:
        return None
    backup = path.with_name(
        f"{path.stem}.before-v{SCHEMA_VERSION}-{datetime.now():%Y%m%d%H%M%S}{path.suffix}"
    )
    c.commit()
    disk = sqlite3.connect(backup)
    c.backup(disk)
    disk.close()
    backup.chmod(0o600)
    c.isolation_level = None
    c.execute("PRAGMA foreign_keys=OFF")
    c.execute("BEGIN IMMEDIATE")
    try:
        for table in changed:
            columns = ",".join(table_columns(c, table))
            sql = re.sub(
                rf"^CREATE TABLE (IF NOT EXISTS )?\"?{table}\"?",
                f"CREATE TABLE _upgrade_{table}",
                wanted[table],
            )
            c.execute(sql)
            c.execute(
                f"INSERT INTO _upgrade_{table}({columns}) SELECT {columns} FROM {table}"
            )
            c.execute(f"DROP TABLE {table}")
            c.execute(f"ALTER TABLE _upgrade_{table} RENAME TO {table}")
        if c.execute("PRAGMA foreign_key_check").fetchone():
            raise CRMError("Upgrade found broken references; nothing was changed.")
        c.execute("COMMIT")
    except Exception:
        c.execute("ROLLBACK")
        raise
    finally:
        c.execute("PRAGMA foreign_keys=ON")
        c.isolation_level = ""
    return backup


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
        schema = Path(__file__).with_name("schema.sql").read_text()
        existed = self.path.exists() and self.path.stat().st_size > 0
        c = sqlite3.connect(self.path)
        try:
            backup = None
            if existed:
                backup = upgrade(c, schema, self.path)
            c.executescript(schema)
            c.execute(
                "UPDATE meta SET value=? WHERE key='schema_version'",
                (str(SCHEMA_VERSION),),
            )
            c.commit()
        finally:
            c.close()
        self.path.chmod(0o600)
        result = {"database": str(self.path), "schema_version": SCHEMA_VERSION}
        if backup:
            result["backup"] = str(backup)
        return result

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
            "interactions",
            "events",
            "sources",
        }:
            raise CRMError("Invalid table.")
        row = c.execute(
            f"SELECT * FROM {table} WHERE id=?", (integer(id, "id"),)
        ).fetchone()
        if row is None:
            raise CRMError(f"{table} record not found.")
        return dict(row)

    # ------------------------------------------------------------ direct records
    # People editing their own records in the dashboard or CLI write directly, with
    # an audit row. Anything sourced from email, forms or Claude still goes through
    # a proposal.

    def _fields(self, c, table, fields):
        allowed = EDITABLE[table]
        unknown = set(fields) - allowed
        if unknown:
            raise CRMError(f"Unknown {table} fields: {', '.join(sorted(unknown))}.")
        clean = {}
        for k, v in fields.items():
            if isinstance(v, str):
                v = v.strip() or None
            if k.endswith(("_date", "_at", "_close")) and v is not None:
                v = iso_date(v, k)
            if k == "tags":
                v = canonical(tags(v))
            if k.endswith("_id") and v is not None:
                integer(v, k)
            clean[k] = v
        for key, ref in (
            ("contact_id", "contacts"),
            ("primary_contact_id", "contacts"),
            ("decision_contact_id", "contacts"),
            ("opportunity_id", "opportunities"),
            ("source_id", "sources"),
        ):
            if clean.get(key) is not None:
                self.one(c, ref, clean[key])
        return clean

    def _insert(self, c, table, values):
        cols = list(values)
        try:
            return c.execute(
                f"INSERT INTO {table}({','.join(cols)}) VALUES({','.join('?' * len(cols))})",
                [values[k] for k in cols],
            ).lastrowid
        except sqlite3.IntegrityError as e:
            raise CRMError(f"Invalid {table} value: {e}.") from e

    def _update(self, c, table, id, values, stamp=True):
        if not values:
            return
        if stamp and "updated_at" in table_columns(c, table):
            values = {**values, "updated_at": now()}
        try:
            c.execute(
                f"UPDATE {table} SET {','.join(k + '=?' for k in values)} WHERE id=?",
                [*values.values(), id],
            )
        except sqlite3.IntegrityError as e:
            raise CRMError(f"Invalid {table} value: {e}.") from e

    def add_account(
        self, name, relationship="unknown", lifecycle="new", actor="human", **fields
    ):
        name = clean_text(name, "name", 200)
        if relationship not in RELATIONSHIPS or lifecycle not in LIFECYCLES:
            raise CRMError("Invalid relationship or lifecycle.")
        with self.connection(True) as c:
            values = self._fields(c, "accounts", fields)
            base = values.get("slug") or slugify(name)
            slug, n = base, 1
            while c.execute("SELECT 1 FROM accounts WHERE slug=?", (slug,)).fetchone():
                if values.get("slug"):
                    raise CRMError("Another relationship already uses that slug.")
                n += 1
                slug = f"{base}-{n}"
            values.update(
                name=name, relationship=relationship, lifecycle=lifecycle, slug=slug
            )
            id = self._insert(c, "accounts", values)
            self.audit(c, actor, "created", "account", id, {"name": name})
        return {"id": id, "slug": slug}

    def update_account(self, id, actor="human", **fields):
        with self.connection(True) as c:
            account = self.one(c, "accounts", id)
            rel = fields.pop("relationship", None)
            if "name" in fields:
                fields["name"] = clean_text(fields["name"], "name", 200)
            values = self._fields(c, "accounts", fields)
            if rel is not None and rel != account["relationship"]:
                if rel not in RELATIONSHIPS:
                    raise CRMError("Invalid relationship.")
                self._guard_relationship(c, id, rel)
                values["relationship"] = rel
            if values.get("lifecycle", account["lifecycle"]) not in LIFECYCLES:
                raise CRMError("Invalid lifecycle.")
            self._update(c, "accounts", id, values)
            self.audit(c, actor, "updated", "account", id, {"fields": sorted(values)})
        return {"id": id}

    @staticmethod
    def _guard_relationship(c, account_id, relationship):
        if relationship not in {"customer", "prospect"} and c.execute(
            "SELECT 1 FROM opportunities WHERE account_id=? AND stage NOT IN ('lost','won','parked')",
            (account_id,),
        ).fetchone():
            raise CRMError(
                "Resolve open sales opportunities before changing this account to a non-buyer relationship."
            )

    def add_contact(self, account_id, name, email=None, actor="human", **fields):
        name = clean_text(name, "name", 200)
        if email:
            email = clean_text(email, "email", 254).lower()
            if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
                raise CRMError("Enter a valid email address.")
        with self.connection(True) as c:
            self.one(c, "accounts", account_id)
            values = self._fields(c, "contacts", fields)
            values.update(account_id=account_id, name=name, email=email or None)
            try:
                id = c.execute(
                    f"INSERT INTO contacts({','.join(values)}) VALUES({','.join('?' * len(values))})",
                    list(values.values()),
                ).lastrowid
            except sqlite3.IntegrityError as e:
                if "email" in str(e):
                    raise CRMError("A contact already uses that email.") from e
                raise CRMError(f"Invalid contacts value: {e}.") from e
            self.audit(c, actor, "created", "contact", id, {"account_id": account_id})
        return {"id": id}

    def update_contact(self, id, actor="human", **fields):
        with self.connection(True) as c:
            self.one(c, "contacts", id)
            if fields.get("email"):
                fields["email"] = clean_text(fields["email"], "email", 254).lower()
            values = self._fields(c, "contacts", fields)
            self._update(c, "contacts", id, values)
            self.audit(c, actor, "updated", "contact", id, {"fields": sorted(values)})
        return {"id": id}

    def add_opportunity(self, account_id, title, stage="discovery", actor="human", **fields):
        title = clean_text(title, "title", 300)
        if stage not in STAGES:
            raise CRMError("Invalid pipeline stage.")
        with self.connection(True) as c:
            account = self.one(c, "accounts", account_id)
            if account["relationship"] not in {"prospect", "customer"}:
                raise CRMError(
                    "Only prospects and customers belong in the sales pipeline."
                )
            values = self._fields(c, "opportunities", fields)
            values.update(account_id=account_id, title=title, stage=stage)
            id = self._insert(c, "opportunities", values)
            self.audit(
                c, actor, "created", "opportunity", id, {"account_id": account_id}
            )
        return {"id": id}

    def update_opportunity(self, id, actor="human", **fields):
        with self.connection(True) as c:
            opp = self.one(c, "opportunities", id)
            values = self._fields(c, "opportunities", fields)
            if "stage" in values:
                if values["stage"] not in STAGES:
                    raise CRMError("Invalid pipeline stage.")
                account = self.one(c, "accounts", opp["account_id"])
                if account["relationship"] not in {"prospect", "customer"}:
                    raise CRMError(
                        "Investors and other non-buyers do not enter the customer pipeline."
                    )
                if values["stage"] in {"won", "lost"} and not opp["closed_at"]:
                    values.setdefault("closed_at", today())
            self._update(c, "opportunities", id, values)
            self.audit(c, actor, "updated", "opportunity", id, {"fields": sorted(values)})
        return {"id": id}

    def log_interaction(
        self,
        account_id,
        summary,
        kind="note",
        direction="internal",
        actor="human",
        **fields,
    ):
        summary = clean_text(summary, "summary", 2000)
        if direction not in {"in", "out", "internal", "unknown"}:
            raise CRMError("Invalid direction.")
        with self.connection(True) as c:
            self.one(c, "accounts", account_id)
            values = self._fields(c, "interactions", fields)
            values.setdefault("occurred_at", now())
            values.update(
                account_id=account_id, summary=summary, kind=kind, direction=direction
            )
            id = self._insert(c, "interactions", values)
            self.audit(c, actor, "logged", "interaction", id, {"kind": kind})
        return {"id": id}

    def find_account(self, ref):
        """An id, slug, exact name, or a name fragment that matches exactly one."""
        with self.connection() as c:
            if isinstance(ref, int) or str(ref).isdigit():
                return self.one(c, "accounts", int(ref))
            ref = str(ref).strip()
            for sql, arg in (
                ("SELECT * FROM accounts WHERE slug=?", ref),
                ("SELECT * FROM accounts WHERE lower(name)=lower(?)", ref),
                ("SELECT * FROM accounts WHERE lower(name) LIKE lower(?)", f"%{ref}%"),
            ):
                rows = c.execute(sql, (arg,)).fetchall()
                if len(rows) == 1:
                    return dict(rows[0])
                if len(rows) > 1:
                    names = ", ".join(r["name"] for r in rows[:6])
                    raise CRMError(f"'{ref}' matches several relationships: {names}.")
        raise CRMError(f"No relationship matches '{ref}'.")

    def find_contact(self, ref):
        with self.connection() as c:
            if isinstance(ref, int) or str(ref).isdigit():
                return self.one(c, "contacts", int(ref))
            ref = str(ref).strip()
            for sql, arg in (
                ("SELECT * FROM contacts WHERE email=? COLLATE NOCASE", ref),
                ("SELECT * FROM contacts WHERE lower(name)=lower(?)", ref),
                ("SELECT * FROM contacts WHERE lower(name) LIKE lower(?)", f"%{ref}%"),
            ):
                rows = c.execute(sql, (arg,)).fetchall()
                if len(rows) == 1:
                    return dict(rows[0])
                if len(rows) > 1:
                    raise CRMError(f"'{ref}' matches several contacts.")
        raise CRMError(f"No contact matches '{ref}'.")

    # ------------------------------------------------------------ tickets
    # What a customer is waiting on. A ticket stays open until someone closes it;
    # the customer being told is recorded separately from the fix.

    def open_ticket(self, account_id, title, actor="human", log=True, **fields):
        title = clean_text(title, "title", 300)
        with self.connection(True) as c:
            self.one(c, "accounts", account_id)
            values = self._fields(c, "tickets", fields)
            if values.get("contact_id"):
                if self.one(c, "contacts", values["contact_id"])["account_id"] != account_id:
                    raise CRMError("That contact belongs to another relationship.")
            values.setdefault("reported_at", today())
            values.update(account_id=account_id, title=title)
            id = self._insert(c, "tickets", values)
            if log:
                # The report is also a conversation; record it once, here.
                self._insert(
                    c,
                    "interactions",
                    {
                        "account_id": account_id,
                        "contact_id": values.get("contact_id"),
                        "kind": "feedback",
                        "channel": values.get("reported_via"),
                        "direction": "in",
                        "occurred_at": values["reported_at"],
                        "summary": f"Reported (ticket #{id}): {title}",
                        "body": values.get("body"),
                    },
                )
            self.audit(c, actor, "opened", "ticket", id, {"account_id": account_id})
        return {"id": id}

    def update_ticket(self, id, actor="human", **fields):
        with self.connection(True) as c:
            self.one(c, "tickets", id)
            values = self._fields(c, "tickets", fields)
            self._update(c, "tickets", id, values)
            self.audit(c, actor, "updated", "ticket", id, {"fields": sorted(values)})
        return {"id": id}

    def set_ticket_status(self, id, status, actor="human", **fields):
        if status not in TICKET_STATUSES:
            raise CRMError(f"Status must be one of {', '.join(sorted(TICKET_STATUSES))}.")
        with self.connection(True) as c:
            ticket = self.one(c, "tickets", id)
            values = self._fields(c, "tickets", fields)
            values["status"] = status
            stamp = now()
            if status in {"fixed", "closed"}:
                values["fixed_at"] = ticket["fixed_at"] or stamp
            if status in CLOSED_TICKET:
                values["closed_at"] = ticket["closed_at"] or stamp
            if status in OPEN_TICKET and (ticket["closed_at"] or ticket["fixed_at"]):
                # Reopened: the earlier fix and update no longer describe it. The audit
                # row keeps what they were.
                values.update(
                    closed_at=None,
                    fixed_at=None,
                    notified_at=None,
                    notified_via=None,
                    notified_note=None,
                    notification_verified=0,
                )
            self._update(c, "tickets", id, values)
            self.audit(
                c,
                actor,
                "status",
                "ticket",
                id,
                {
                    "from": ticket["status"],
                    "to": status,
                    "previous": {
                        k: ticket[k] for k in ("fixed_at", "closed_at", "notified_at")
                    },
                },
            )
        return {"id": id, "status": status}

    def close_ticket(self, id, status="closed", actor="human", **fields):
        if status not in CLOSED_TICKET:
            raise CRMError("Close as closed, wont_do or duplicate.")
        return self.set_ticket_status(id, status, actor, **fields)

    def notify_ticket(self, id, via, note, at=None, contact_id=None, actor="human"):
        """A person records that they told the customer, how, and what they said.

        This is attested by the person, not verified; Gmail-sourced proposals are the
        verified path. Either way the fix must be recorded first."""
        note = clean_text(note, "note", 2000)
        if via not in CHANNELS:
            raise CRMError(f"via must be one of {', '.join(sorted(CHANNELS))}.")
        at = iso_date(at, "at") or now()
        with self.connection(True) as c:
            ticket = self.one(c, "tickets", id)
            if not ticket["fixed_at"] and ticket["status"] not in {"fixed", "closed"}:
                raise CRMError("Record the fix before telling the customer it is done.")
            contact_id = contact_id or ticket["contact_id"]
            if contact_id and self.one(c, "contacts", contact_id)["account_id"] != ticket["account_id"]:
                raise CRMError("That contact belongs to another relationship.")
            self._update(
                c,
                "tickets",
                id,
                {
                    "notified_at": at,
                    "notified_via": via,
                    "notified_note": note,
                    "notification_verified": 0,
                },
            )
            self._insert(
                c,
                "interactions",
                {
                    "account_id": ticket["account_id"],
                    "contact_id": contact_id,
                    "kind": "update_sent",
                    "channel": via,
                    "direction": "out",
                    "occurred_at": at,
                    "summary": f"Told the customer about ticket #{id}: {ticket['title']}",
                    "body": note,
                },
            )
            self.audit(c, actor, "notified", "ticket", id, {"via": via, "attested": True})
        return {"id": id, "notified_at": at, "verified": False}

    def tickets(self, include_closed=False, account_id=None):
        where, args = [], []
        if not include_closed:
            where.append("t.status NOT IN ('closed','wont_do','duplicate')")
        if account_id:
            where.append("t.account_id=?")
            args.append(account_id)
        with self.connection() as c:
            return [
                dict(r)
                for r in c.execute(
                    TICKET_SELECT
                    + (" WHERE " + " AND ".join(where) if where else "")
                    + TICKET_ORDER,
                    args,
                )
            ]

    def untold(self):
        """Fixed or closed, and the customer has not been told."""
        with self.connection() as c:
            return [
                dict(r)
                for r in c.execute(
                    TICKET_SELECT
                    + " WHERE (t.fixed_at IS NOT NULL OR t.status IN ('fixed','closed'))"
                    " AND t.notified_at IS NULL AND t.status NOT IN ('wont_do','duplicate')"
                    " ORDER BY COALESCE(t.fixed_at,t.closed_at,t.updated_at,t.created_at)"
                )
            ]

    def ticket(self, id):
        with self.connection() as c:
            t = self.one(c, "tickets", id)
            t["account_name"] = self.one(c, "accounts", t["account_id"])["name"]
            t["custom"] = self._custom(c, "ticket", id)
            t["history"] = [
                dict(r)
                for r in c.execute(
                    "SELECT * FROM audit WHERE object_type='ticket' AND object_id=? ORDER BY id",
                    (id,),
                )
            ]
        return t

    # ------------------------------------------------------------ qualification
    # Commercial KYC: can and will this account buy? Generic questions plus any
    # custom account fields marked as qualification questions.

    def _qualification_questions(self, c):
        custom = [
            (r["key"], r["label"], "custom")
            for r in c.execute(
                "SELECT key,label FROM field_definitions WHERE object_type='account' AND qualification=1 ORDER BY id"
            )
        ]
        return [(k, l, "core") for k, l in QUALIFICATION_CORE] + custom

    def _qualification_status(self, c, account_id):
        row = c.execute(
            "SELECT * FROM qualification WHERE account_id=?", (account_id,)
        ).fetchone()
        custom = self._custom(c, "account", account_id)
        questions = self._qualification_questions(c)
        missing = [
            k
            for k, _, where in questions
            if (row[k] if where == "core" and row else custom.get(k) if where == "custom" else None)
            is None
        ]
        total = len(questions)
        filled = total - len(missing)
        status = (
            "not_started"
            if filled == 0
            else "thin"
            if filled < total / 2
            else "partial"
            if filled < total
            else "complete"
        )
        return {
            "filled": filled,
            "total": total,
            "pct": round(100 * filled / total) if total else 0,
            "status": status,
            "missing": missing,
            "confidence": row["confidence"] if row else "low",
        }

    def set_qualification(self, account_id, actor="human", **fields):
        with self.connection(True) as c:
            self.one(c, "accounts", account_id)
            custom_keys = {
                k for k, _, where in self._qualification_questions(c) if where == "custom"
            }
            custom = {k: fields.pop(k) for k in list(fields) if k in custom_keys}
            values = self._fields(c, "qualification", fields)
            if not c.execute(
                "SELECT 1 FROM qualification WHERE account_id=?", (account_id,)
            ).fetchone():
                self._insert(c, "qualification", {"account_id": account_id})
            if values:
                values["updated_at"] = now()
                try:
                    c.execute(
                        f"UPDATE qualification SET {','.join(k + '=?' for k in values)} WHERE account_id=?",
                        [*values.values(), account_id],
                    )
                except sqlite3.IntegrityError as e:
                    raise CRMError(f"Invalid qualification value: {e}.") from e
            for k, v in custom.items():
                self._set_custom(c, "account", account_id, k, v)
            self.audit(
                c,
                actor,
                "qualified",
                "account",
                account_id,
                {"fields": sorted([*values, *custom])},
            )
            return self._qualification_status(c, account_id)

    def add_evidence(self, account_id, claim, source, url=None, observed_at=None, actor="human"):
        claim = clean_text(claim, "claim", 2000)
        source = clean_text(source, "source", 500)
        with self.connection(True) as c:
            self.one(c, "accounts", account_id)
            id = self._insert(
                c,
                "qualification_evidence",
                {
                    "account_id": account_id,
                    "claim": claim,
                    "source": source,
                    "url": url,
                    "observed_at": iso_date(observed_at, "observed_at"),
                },
            )
            self.audit(c, actor, "evidence", "account", account_id, {"evidence_id": id})
        return {"id": id}

    def qualification(self, account_id):
        with self.connection() as c:
            self.one(c, "accounts", account_id)
            row = c.execute(
                "SELECT * FROM qualification WHERE account_id=?", (account_id,)
            ).fetchone()
            custom = self._custom(c, "account", account_id)
            return {
                "record": dict(row) if row else None,
                "questions": [
                    {
                        "key": k,
                        "label": l,
                        "where": w,
                        "value": (row[k] if row else None) if w == "core" else custom.get(k),
                    }
                    for k, l, w in self._qualification_questions(c)
                ],
                "evidence": [
                    dict(r)
                    for r in c.execute(
                        "SELECT * FROM qualification_evidence WHERE account_id=? ORDER BY id",
                        (account_id,),
                    )
                ],
                "status": self._qualification_status(c, account_id),
            }

    def qualification_gaps(self):
        """Buyers still missing qualification answers; customers and pilots first."""
        with self.connection() as c:
            out = []
            for a in c.execute(
                "SELECT id,name,relationship,lifecycle FROM accounts WHERE relationship IN ('prospect','customer')"
                " AND lifecycle NOT IN ('lost','not_a_fit','internal','closed','churned')"
            ).fetchall():
                s = self._qualification_status(c, a["id"])
                if s["status"] != "complete":
                    out.append({**dict(a), **s})
        rank = {"active": 0, "pilot": 1, "qualified": 2, "engaged": 3}
        return sorted(out, key=lambda r: (rank.get(r["lifecycle"], 4), r["pct"], r["name"]))

    # ------------------------------------------------------------ custom fields

    def define_field(
        self,
        object_type,
        key,
        label,
        type="text",
        choices=None,
        qualification=False,
        help=None,
        actor="human",
    ):
        if object_type not in OBJECT_TABLES:
            raise CRMError(f"object_type must be one of {', '.join(sorted(OBJECT_TABLES))}.")
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", key or ""):
            raise CRMError("key must be lower_snake_case, starting with a letter.")
        if object_type == "account" and key in EDITABLE["accounts"] | EDITABLE["qualification"]:
            raise CRMError(f"'{key}' is already a built-in field.")
        if type not in FIELD_TYPES:
            raise CRMError(f"type must be one of {', '.join(sorted(FIELD_TYPES))}.")
        if type == "choice" and not (isinstance(choices, list) and choices):
            raise CRMError("A choice field needs a list of choices.")
        if qualification and object_type != "account":
            raise CRMError("Only account fields can be qualification questions.")
        label = clean_text(label, "label", 200)
        with self.connection(True) as c:
            prior = c.execute(
                "SELECT * FROM field_definitions WHERE object_type=? AND key=?",
                (object_type, key),
            ).fetchone()
            values = {
                "label": label,
                "type": type,
                "choices": canonical(choices) if choices else None,
                "qualification": int(bool(qualification)),
                "help": help,
            }
            if prior:
                if prior["type"] != type and c.execute(
                    "SELECT 1 FROM custom_values WHERE object_type=? AND key=?",
                    (object_type, key),
                ).fetchone():
                    raise CRMError("This field already holds values; its type cannot change.")
                if all(prior[k] == v for k, v in values.items()):
                    return {"id": prior["id"], "changed": False}
                c.execute(
                    f"UPDATE field_definitions SET {','.join(k + '=?' for k in values)} WHERE id=?",
                    [*values.values(), prior["id"]],
                )
                id = prior["id"]
            else:
                id = self._insert(
                    c,
                    "field_definitions",
                    {"object_type": object_type, "key": key, **values},
                )
            self.audit(c, actor, "defined", "field", id, {"object_type": object_type, "key": key})
        return {"id": id, "changed": True}

    def fields(self, object_type=None):
        with self.connection() as c:
            rows = c.execute(
                "SELECT f.*,(SELECT count(*) FROM custom_values v WHERE v.object_type=f.object_type AND v.key=f.key) AS used"
                " FROM field_definitions f"
                + (" WHERE object_type=?" if object_type else "")
                + " ORDER BY object_type,id",
                (object_type,) if object_type else (),
            )
            return [
                {**dict(r), "choices": json.loads(r["choices"]) if r["choices"] else None}
                for r in rows
            ]

    def set_custom(self, object_type, object_id, key, value, actor="human"):
        with self.connection(True) as c:
            self._set_custom(c, object_type, object_id, key, value)
            self.audit(c, actor, "custom", object_type, object_id, {"key": key})
        return {"object_type": object_type, "id": object_id, "key": key}

    def _set_custom(self, c, object_type, object_id, key, value):
        if object_type not in OBJECT_TABLES:
            raise CRMError("Unknown record type.")
        self.one(c, OBJECT_TABLES[object_type], object_id)
        f = c.execute(
            "SELECT * FROM field_definitions WHERE object_type=? AND key=?",
            (object_type, key),
        ).fetchone()
        if f is None:
            raise CRMError(f"Define the {object_type} field '{key}' first.")
        if value is None or value == "":
            c.execute(
                "DELETE FROM custom_values WHERE object_type=? AND object_id=? AND key=?",
                (object_type, object_id, key),
            )
            return
        value = coerce(f, value)
        c.execute(
            "INSERT INTO custom_values(object_type,object_id,key,value) VALUES(?,?,?,?)"
            " ON CONFLICT(object_type,object_id,key) DO UPDATE SET value=excluded.value,updated_at=CURRENT_TIMESTAMP",
            (object_type, object_id, key, canonical(value)),
        )

    @staticmethod
    def _custom(c, object_type, object_id):
        return {
            r["key"]: json.loads(r["value"])
            for r in c.execute(
                "SELECT key,value FROM custom_values WHERE object_type=? AND object_id=?",
                (object_type, object_id),
            )
        }

    # ------------------------------------------------------------ sources and events

    def add_source(self, slug, label, category="other", actor="human", **fields):
        with self.connection(True) as c:
            id = self._insert(
                c,
                "sources",
                {
                    "slug": clean_text(slug, "slug", 80),
                    "label": clean_text(label, "label", 200),
                    "category": category,
                    **{k: fields[k] for k in fields if k in {"is_public", "url", "notes"}},
                },
            )
            self.audit(c, actor, "created", "source", id, {"slug": slug})
        return {"id": id}

    def add_event(self, slug, name, actor="human", **fields):
        with self.connection(True) as c:
            values = self._fields(c, "events", fields)
            values.update(slug=clean_text(slug, "slug", 80), name=clean_text(name, "name", 200))
            id = self._insert(c, "events", values)
            self.audit(c, actor, "created", "event", id, {"slug": slug})
        return {"id": id}

    def met_at_event(self, event_id, contact_id, actor="human", **fields):
        with self.connection(True) as c:
            self.one(c, "events", event_id)
            self.one(c, "contacts", contact_id)
            values = {k: fields[k] for k in fields if k in {"met_at", "met_context", "followed_up", "notes"}}
            c.execute(
                "INSERT OR IGNORE INTO event_contacts(event_id,contact_id) VALUES(?,?)",
                (event_id, contact_id),
            )
            if values:
                c.execute(
                    f"UPDATE event_contacts SET {','.join(k + '=?' for k in values)} WHERE event_id=? AND contact_id=?",
                    [*values.values(), event_id, contact_id],
                )
            self.audit(c, actor, "met", "event", event_id, {"contact_id": contact_id})
        return {"event_id": event_id, "contact_id": contact_id}

    def update_record(self, object_type, id, actor="human", **values):
        """Set built-in fields and custom fields on one record in a single call."""
        table = OBJECT_TABLES.get(object_type)
        if not table:
            raise CRMError("Unknown record type.")
        with self.connection() as c:
            self.one(c, table, id)
            defined = {
                r["key"]
                for r in c.execute(
                    "SELECT key FROM field_definitions WHERE object_type=?", (object_type,)
                )
            }
        builtin = EDITABLE[table] | ({"relationship"} if table == "accounts" else set())
        unknown = set(values) - builtin - defined
        if unknown:
            raise CRMError(
                f"Unknown {object_type} fields: {', '.join(sorted(unknown))}. "
                "Define a custom field first if this is your own data."
            )
        core = {k: v for k, v in values.items() if k in builtin}
        if core:
            {
                "account": self.update_account,
                "contact": self.update_contact,
                "opportunity": self.update_opportunity,
                "ticket": self.update_ticket,
            }.get(object_type, self._update_plain(table))(id, actor=actor, **core)
        for k, v in values.items():
            if k not in builtin:
                self.set_custom(object_type, id, k, v, actor=actor)
        return {"object_type": object_type, "id": id, "fields": sorted(values)}

    def _update_plain(self, table):
        def run(id, actor="human", **fields):
            with self.connection(True) as c:
                values = self._fields(c, table, fields)
                self._update(c, table, id, values)
                self.audit(c, actor, "updated", table, id, {"fields": sorted(values)})

        return run

    # ------------------------------------------------------------ follow-ups

    def followups(self):
        """Every dated next step in one list: tasks, opportunities, relationships, tickets."""
        with self.connection() as c:
            return [dict(r) for r in c.execute(FOLLOWUPS_SQL)]

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
        optional = {
            "create_task": {"due_date"},
            "open_ticket": {"kind", "severity", "area", "body", "reported_via"},
        }.get(action, set())
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
        for k, allowed in (
            ("kind", TICKET_KINDS),
            ("severity", SEVERITIES),
            ("reported_via", CHANNELS),
        ):
            if k in payload and payload[k] not in allowed:
                raise CRMError(f"Invalid {k}.")
        for k in ("area", "body"):
            if k in payload:
                clean_text(payload[k], k, 20000)
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
                extra = {
                    k: data[k]
                    for k in ("kind", "severity", "area", "body", "reported_via")
                    if k in data
                }
                self._insert(
                    c,
                    "tickets",
                    {
                        "account_id": data["account_id"],
                        "title": data["title"],
                        "proposal_id": id,
                        "reported_at": today(),
                        **extra,
                    },
                )
            elif action == "record_fix":
                self.one(c, "tickets", data["ticket_id"])
                c.execute(
                    "UPDATE tickets SET status='fixed',fixed_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP WHERE id=?",
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
                    "UPDATE tickets SET notified_at=CURRENT_TIMESTAMP,notified_via='email',"
                    "notified_note=?,notification_verified=1,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (source["subject"], data["ticket_id"]),
                )
            elif action == "set_relationship":
                self._guard_relationship(c, data["account_id"], data["relationship"])
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
                    "SELECT a.*,count(c.id) AS contact_count,"
                    "(SELECT max(COALESCE(i.occurred_at,i.created_at)) FROM interactions i WHERE i.account_id=a.id) AS last_interaction_at"
                    " FROM accounts a LEFT JOIN contacts c ON c.account_id=a.id GROUP BY a.id ORDER BY a.id DESC"
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
                    TICKET_SELECT + TICKET_ORDER
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
            followups=self.followups(),
            untold=self.untold(),
            qualification_gaps=self.qualification_gaps(),
            fields=self.fields(),
            schema_version=SCHEMA_VERSION,
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
                    "SELECT * FROM interactions WHERE account_id=? ORDER BY COALESCE(occurred_at,created_at) DESC,id DESC",
                    (id,),
                )
            ]
            account["opportunities"] = [
                dict(r)
                for r in c.execute(
                    "SELECT * FROM opportunities WHERE account_id=? ORDER BY id", (id,)
                )
            ]
            account["custom"] = self._custom(c, "account", id)
            account["events"] = [
                dict(r)
                for r in c.execute(
                    "SELECT e.name,e.start_date,ec.* FROM event_contacts ec JOIN events e ON e.id=ec.event_id"
                    " JOIN contacts p ON p.id=ec.contact_id WHERE p.account_id=?",
                    (id,),
                )
            ]
            for person in account["contacts"]:
                person["custom"] = self._custom(c, "contact", person["id"])
            account["tasks"] = [
                dict(r)
                for r in c.execute("SELECT * FROM tasks WHERE account_id=?", (id,))
            ]
            account["tickets"] = [
                dict(r)
                for r in c.execute(
                    "SELECT * FROM tickets WHERE account_id=? ORDER BY id DESC", (id,)
                )
            ]
        account["qualification"] = self.qualification(id)
        return account
