import argparse
import json
import sys
from .core import Store, CRMError


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
        elif args.command == "gmail-auth":
            from .integrations import gmail_auth

            result = gmail_auth(store, args.client_secrets)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except (CRMError, json.JSONDecodeError) as e:
        print(str(e), file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
