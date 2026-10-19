"""Synthetic demo data only. No imports from Altys systems or private records."""

from datetime import date, timedelta
from .core import CRMError


def seed_demo(store):
    store.init()
    if store.dashboard()["counts"]["accounts"]:
        raise CRMError(
            "Demo seed only runs on an empty database. Choose a new --db path."
        )
    today = date.today()
    a = store.add_account("Northstar Studio", "customer", "active")["id"]
    b = store.add_account("Paper Kite", "prospect", "engaged")["id"]
    inv = store.add_account("Fieldwork Capital", "investor", "engaged")["id"]
    v = store.add_account("Signal Post", "vendor", "active")["id"]
    for id, name, email in [
        (a, "Maya Rao", "maya@northstar.example"),
        (b, "Sam Chen", "sam@paperkite.example"),
        (inv, "Alex Reed", "alex@fieldwork.example"),
        (v, "Signal Post", "updates@signalpost.example"),
    ]:
        store.add_contact(id, name, email)
    store.add_opportunity(b, "First team workspace", "demo")

    def evidence(id, subject, sender, body):
        return store.ingest("demo", id, subject, sender, body)["id"]

    def applied(i, act, p):
        pid = store.propose(i, act, p, actor="demo")["id"]
        store.apply(pid, confirm=True)
        return pid

    i = evidence(
        "conversation-01",
        "The export is working now",
        "maya@northstar.example",
        "The account export is now working. Could you let the rest of our team know?",
    )
    applied(
        i,
        "log_interaction",
        {
            "account_id": a,
            "summary": "Maya confirmed the export works; team update still owed.",
        },
    )
    applied(
        i,
        "create_task",
        {
            "account_id": a,
            "title": "Send the team an update about the export fix",
            "due_date": str(today),
        },
    )
    applied(
        i,
        "open_ticket",
        {"account_id": a, "title": "Account export failed for a customer"},
    )
    with store.connection() as c:
        ticket = c.execute("SELECT id FROM tickets LIMIT 1").fetchone()["id"]
    applied(i, "record_fix", {"ticket_id": ticket})
    i2 = evidence(
        "inbound-02",
        "Could we try this with our team?",
        "sam@paperkite.example",
        "We have six people working across spreadsheets. Could we arrange a product demo next week?",
    )
    store.propose(
        i2,
        "create_task",
        {
            "account_id": b,
            "title": "Offer Sam two demo times",
            "due_date": str(today + timedelta(days=1)),
        },
        actor="demo",
    )
    i3 = evidence(
        "investor-03",
        "Happy to compare notes",
        "alex@fieldwork.example",
        "Thanks for the introduction. Happy to compare notes about the fundraise; what time works?",
    )
    store.propose(
        i3,
        "log_interaction",
        {
            "account_id": inv,
            "summary": "Investor is open to a call; a time has not been agreed.",
        },
        actor="demo",
    )
    i4 = evidence(
        "provider-04",
        "Your weekly product digest",
        "updates@signalpost.example",
        "Here are this week’s product updates. You can explore our new reporting features.",
    )
    store.propose(
        i4,
        "set_relationship",
        {"account_id": v, "relationship": "prospect"},
        actor="demo",
    )
    i5 = evidence(
        "internal-05",
        "Fix shipped; tell the client",
        "",
        "The export fix is deployed. There is no sent customer email attached to this note.",
    )
    store.propose(i5, "record_notification", {"ticket_id": ticket}, actor="demo")
    applied(
        i3,
        "create_task",
        {
            "account_id": inv,
            "title": "Offer Alex a time to compare notes",
            "due_date": str(today - timedelta(days=1)),
        },
    )
    with store.connection(True) as c:
        c.execute("INSERT OR REPLACE INTO meta VALUES('demo','1')")
    return {
        "demo": True,
        "note": "Every person, firm, address and conversation in this database is fictional.",
    }
