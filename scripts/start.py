#!/usr/bin/env python3
"""Start the dashboard without installing packages or connecting any accounts."""

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys


def ensure_python():
    if sys.version_info >= (3, 11):
        return
    candidates = [
        shutil.which(name)
        for name in ("python3.14", "python3.13", "python3.12", "python3.11")
    ]
    uv = shutil.which("uv")
    if uv:
        result = subprocess.run(
            [uv, "python", "find", "--offline", "3.12"], capture_output=True, text=True
        )
        if result.returncode == 0:
            candidates.append(result.stdout.strip())
    for candidate in candidates:
        if not candidate:
            continue
        result = subprocess.run(
            [
                candidate,
                "-c",
                "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)",
            ],
            capture_output=True,
        )
        if result.returncode == 0:
            os.execv(
                candidate, [candidate, str(Path(__file__).resolve()), *sys.argv[1:]]
            )
    raise SystemExit(
        "Python 3.11+ is required. Install it, then run: python3.12 scripts/start.py\nNo runtime, packages or credentials have been downloaded."
    )


def main():
    ensure_python()
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    from loop_crm.core import Store, CRMError
    from loop_crm.demo import seed_demo
    from loop_crm.web import serve

    parser = argparse.ArgumentParser(
        description="Open Loop CRM locally. Defaults to a fictional demo."
    )
    parser.add_argument(
        "--empty",
        action="store_true",
        help="Use your empty personal workspace instead of the demo",
    )
    parser.add_argument(
        "--db",
        help="Optional SQLite path; relative paths are relative to this checkout",
    )
    parser.add_argument("--port", type=int, default=4780)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("--port must be 1–65535")
    path = root / (args.db or ("data/crm.db" if args.empty else "data/demo.db"))
    store = Store(path)
    try:
        if not store.path.exists() and not args.empty:
            seed_demo(store)
        else:
            store.init()
        print(
            "Loop CRM by Altys · "
            + ("personal workspace" if args.empty else "demo workspace"),
            flush=True,
        )
        print(
            "No external account is connected automatically. Stop with Ctrl+C.",
            flush=True,
        )
        serve(store, args.port)
    except CRMError as error:
        raise SystemExit(str(error)) from error
    except OSError as error:
        raise SystemExit(
            f"Could not start the local dashboard: {error}. Try --port 4782 if the port is in use."
        ) from error


if __name__ == "__main__":
    main()
