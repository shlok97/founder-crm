import argparse
import json
import sys
from .core import Store, CRMError, CHANNELS, TICKET_KINDS, SEVERITIES, TICKET_STATUSES


class Text(str):
    """Plain output for list commands; everything else prints JSON."""


def pairs(items):
    out = {}
    for item in items or []:
        if "=" not in item:
            raise CRMError(f"Expected key=value, got {item!r}.")
        k, v = item.split("=", 1)
        out[k.strip()] = v
    return out


def cell(value):
    if value is None:
        return "-"
    if isinstance(value, list):
        return ", ".join(map(str, value)) or "-"
    return str(value)


def lines(rows, cols, empty="Nothing here."):
    if not rows:
        return Text(empty)
    return Text(
        "\n".join(" | ".join(cell(r.get(c)) for c in cols) for r in rows)
    )


def add_workflow_commands(sub):
    t = sub.add_parser("ticket", help="What a customer is waiting on")
    ts = t.add_subparsers(dest="action", required=True)
    a = ts.add_parser("add")
    a.add_argument("title")
    a.add_argument("--account", help="id, slug or name (or give --contact)")
    a.add_argument("--contact")
    a.add_argument("--kind", choices=sorted(TICKET_KINDS), default="bug")
    a.add_argument("--severity", choices=sorted(SEVERITIES), default="normal")
    a.add_argument("--area")
    a.add_argument("--via", choices=sorted(CHANNELS), help="how it was reported")
    a.add_argument("--body", help="what they said, verbatim where you have it")
    a.add_argument("--expected")
    a.add_argument("--owner")
    a.add_argument("--next-action")
    a.add_argument("--due", help="next action date, YYYY-MM-DD")
    a.add_argument("--reported-at")
    a.add_argument("--set", action="append", metavar="KEY=VALUE", help="any other field, built-in or custom")
    for name in ("show",):
        ts.add_parser(name).add_argument("id", type=int)
    st = ts.add_parser("status")
    st.add_argument("id", type=int)
    st.add_argument("status", choices=sorted(TICKET_STATUSES))
    cl = ts.add_parser("close")
    cl.add_argument("id", type=int)
    cl.add_argument("--resolution", help="what changed, in the customer's words")
    cl.add_argument("--release")
    cl.add_argument("--commit")
    cl.add_argument("--evidence")
    cl.add_argument("--as", dest="as_status", choices=["closed", "wont_do", "duplicate"], default="closed")
    n = ts.add_parser("notify", help="record that you told the customer")
    n.add_argument("id", type=int)
    n.add_argument("--via", required=True, choices=sorted(CHANNELS))
    n.add_argument("--note", required=True, help="what you told them")
    n.add_argument("--at")
    n.add_argument("--contact")
    se = ts.add_parser("set")
    se.add_argument("id", type=int)
    se.add_argument("fields", nargs="+", metavar="KEY=VALUE")
    tl = sub.add_parser("tickets", help="Open tickets, worst first")
    tl.add_argument("--all", action="store_true")
    tl.add_argument("--account")
    sub.add_parser("untold", help="Fixed, but the customer was never told")
    sub.add_parser("followups", help="Every dated next step")
    q = sub.add_parser("qualify", help="Commercial qualification (KYC)")
    qs = q.add_subparsers(dest="action", required=True)
    qs.add_parser("gaps")
    qs.add_parser("show").add_argument("account")
    qset = qs.add_parser("set")
    qset.add_argument("account")
    qset.add_argument("fields", nargs="+", metavar="KEY=VALUE")
    qe = qs.add_parser("evidence")
    qe.add_argument("account")
    qe.add_argument("claim")
    qe.add_argument("--source", required=True)
    qe.add_argument("--url")
    qe.add_argument("--at")
    f = sub.add_parser("field", help="Your own fields on any record")
    fs = f.add_subparsers(dest="action", required=True)
    fd = fs.add_parser("define")
    fd.add_argument("object_type")
    fd.add_argument("key")
    fd.add_argument("label")
    fd.add_argument("--type", default="text")
    fd.add_argument("--choices", help="comma-separated, for --type choice")
    fd.add_argument("--qualification", action="store_true", help="count toward qualification")
    fd.add_argument("--help-text")
    fs.add_parser("list").add_argument("object_type", nargs="?")
    sh = sub.add_parser("show", help="A relationship's full record")
    sh.add_argument("account")
    sv = sub.add_parser("set", help="Set fields on a relationship, contact or opportunity")
    sv.add_argument("ref", help="account ref, or contact:<id> / opportunity:<id>")
    sv.add_argument("fields", nargs="+", metavar="KEY=VALUE")
    lg = sub.add_parser("log", help="Record an interaction")
    lg.add_argument("kind")
    lg.add_argument("--account", required=True)
    lg.add_argument("--summary", required=True)
    lg.add_argument("--channel", choices=sorted(CHANNELS))
    lg.add_argument("--direction", default="internal", choices=["in", "out", "internal", "unknown"])
    lg.add_argument("--at")
    lg.add_argument("--contact")
    lg.add_argument("--body")


def _ticket(store, args):
    if args.action == "add":
        if not (args.account or args.contact):
            raise CRMError("Give --account or --contact.")
        contact = store.find_contact(args.contact) if args.contact else None
        account = (
            store.find_account(args.account)
            if args.account
            else store.find_account(contact["account_id"])
        )
        fields = {
            "kind": args.kind,
            "severity": args.severity,
            "area": args.area,
            "reported_via": args.via,
            "body": args.body,
            "expected": args.expected,
            "owner": args.owner,
            "next_action": args.next_action,
            "next_action_date": args.due,
            "reported_at": args.reported_at,
        }
        if contact:
            fields["contact_id"] = contact["id"]
        fields = {k: v for k, v in fields.items() if v is not None}
        extra = pairs(args.set)
        result = store.open_ticket(account["id"], args.title, **fields)
        if extra:
            store.update_record("ticket", result["id"], **extra)
        return {**result, "account": account["name"]}
    if args.action == "show":
        return store.ticket(args.id)
    if args.action == "status":
        return store.set_ticket_status(args.id, args.status)
    if args.action == "close":
        fields = {
            "resolution": args.resolution,
            "release_ref": args.release,
            "commit_ref": args.commit,
            "evidence": args.evidence,
        }
        return store.close_ticket(
            args.id, args.as_status, **{k: v for k, v in fields.items() if v}
        )
    if args.action == "notify":
        contact = store.find_contact(args.contact)["id"] if args.contact else None
        return store.notify_ticket(args.id, args.via, args.note, args.at, contact)
    if args.action == "set":
        return store.update_record("ticket", args.id, **pairs(args.fields))


def _qualify(store, args):
    if args.action == "gaps":
        return lines(
            store.qualification_gaps(),
            ["name", "lifecycle", "pct", "status", "missing"],
            "Every buyer is fully qualified.",
        )
    account = store.find_account(args.account)
    if args.action == "show":
        return store.qualification(account["id"])
    if args.action == "set":
        return store.set_qualification(account["id"], **pairs(args.fields))
    return store.add_evidence(account["id"], args.claim, args.source, args.url, args.at)


def _field(store, args):
    if args.action == "list":
        return store.fields(args.object_type)
    return store.define_field(
        args.object_type,
        args.key,
        args.label,
        args.type,
        [c.strip() for c in args.choices.split(",")] if args.choices else None,
        args.qualification,
        args.help_text,
    )


def _set(store, args):
    kind, _, id = args.ref.partition(":")
    if kind in {"contact", "opportunity", "ticket"} and id.isdigit():
        return store.update_record(kind, int(id), **pairs(args.fields))
    return store.update_record("account", store.find_account(args.ref)["id"], **pairs(args.fields))


def _log(store, args):
    account = store.find_account(args.account)
    fields = {"channel": args.channel, "occurred_at": args.at, "body": args.body}
    if args.contact:
        fields["contact_id"] = store.find_contact(args.contact)["id"]
    return store.log_interaction(
        account["id"],
        args.summary,
        args.kind,
        args.direction,
        **{k: v for k, v in fields.items() if v is not None},
    )


WORKFLOW = {
    "ticket": _ticket,
    "tickets": lambda store, args: lines(
        store.tickets(
            args.all, store.find_account(args.account)["id"] if args.account else None
        ),
        ["id", "severity", "status", "kind", "account_name", "title", "next_action", "next_action_date"],
        "No open tickets.",
    ),
    "untold": lambda store, args: lines(
        store.untold(),
        ["id", "account_name", "status", "title", "resolution", "release_ref", "contact_name"],
        "Every fix has been told to its customer.",
    ),
    "followups": lambda store, args: lines(
        store.followups(),
        ["due", "kind", "account_name", "what", "next_action"],
        "No dated next steps.",
    ),
    "qualify": _qualify,
    "field": _field,
    "show": lambda store, args: store.account_history(store.find_account(args.account)["id"]),
    "set": _set,
    "log": _log,
}


def main():
    p = argparse.ArgumentParser(
        description="Founder CRM: local startup relationships, promises and evidence."
    )
    p.add_argument(
        "--db", help="SQLite path; defaults to FOUNDER_CRM_DB or data/crm.db"
    )
    sub = p.add_subparsers(dest="command", required=True)
    for name in ["init", "demo", "dashboard", "mcp"]:
        sub.add_parser(name)
    serve = sub.add_parser("serve")
    serve.add_argument("--port", type=int, default=4780)
    a = sub.add_parser("account")
    a.add_argument("name")
    a.add_argument("--relationship", default="unknown")
    a.add_argument("--lifecycle", default="new")
    n = sub.add_parser("note")
    n.add_argument("--id", required=True)
    n.add_argument("--subject", required=True)
    n.add_argument("--body", required=True)
    n.add_argument("--sender", default="")
    prop = sub.add_parser("propose")
    prop.add_argument("intake_id", type=int)
    prop.add_argument("action")
    prop.add_argument("payload", help="JSON object")
    for name in ["apply", "reject", "judge"]:
        cmd = sub.add_parser(name)
        cmd.add_argument("id", type=int)
        if name == "apply":
            cmd.add_argument("--confirm", action="store_true")
    gmail = sub.add_parser("gmail-pull")
    gmail.add_argument("--query", default="in:inbox newer_than:14d")
    gmail.add_argument("--limit", type=int, default=20)
    auth = sub.add_parser("gmail-auth")
    auth.add_argument(
        "--client-secrets",
        required=True,
        help="Google Desktop OAuth client JSON; never commit it",
    )
    add_workflow_commands(sub)
    args = p.parse_args()
    store = Store(args.db)
    try:
        if args.command == "init":
            result = store.init()
        elif args.command == "demo":
            from .demo import seed_demo

            result = seed_demo(store)
        elif args.command == "serve":
            from .web import serve

            serve(store, args.port)
            return
        elif args.command == "mcp":
            from .mcp_server import run

            run(store)
            return
        elif args.command == "dashboard":
            result = store.dashboard()
        elif args.command == "account":
            result = store.add_account(args.name, args.relationship, args.lifecycle)
        elif args.command == "note":
            result = store.ingest(
                "claude_code", args.id, args.subject, args.sender, args.body, "internal"
            )
        elif args.command == "propose":
            result = store.propose(
                args.intake_id, args.action, json.loads(args.payload)
            )
        elif args.command == "apply":
            result = store.apply(args.id, confirm=args.confirm)
        elif args.command == "reject":
            result = store.reject(args.id)
        elif args.command == "judge":
            from .judge import judge_proposal

            result = judge_proposal(store, args.id)
        elif args.command == "gmail-pull":
            from .integrations import sync_gmail

            result = sync_gmail(store, args.query, args.limit)
        elif args.command in WORKFLOW:
            result = WORKFLOW[args.command](store, args)
            if isinstance(result, Text):
                print(result)
                return
        elif args.command == "gmail-auth":
            from .integrations import gmail_auth

            result = gmail_auth(store, args.client_secrets)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except (CRMError, json.JSONDecodeError) as e:
        print(str(e), file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
