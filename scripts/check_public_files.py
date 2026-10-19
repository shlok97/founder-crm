"""Check the exact source-release allowlist; never inspect private runtime data."""

from pathlib import Path
import argparse
import re
import subprocess
import sys

from package_release import FILES, ROOT

PATTERNS = {
    "credential": re.compile(
        r"\b(?:ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{30,}|sk-ant-[A-Za-z0-9_-]{20,}|sk-proj-[A-Za-z0-9_-]{20,}|AKIA[A-Z0-9]{16})\b"
    ),
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "local user path": re.compile(
        r"(?:/Users/[a-zA-Z0-9_-]+/|/private/(?:tmp|var)/|/home/[a-zA-Z0-9_-]+/)"
    ),
}


def private_terms():
    """Names and emails from your own CRM database, to keep out of the public repo.

    Opt in per clone: git config founder-crm.privateDb /absolute/path/to/crm.db
    Internal accounts (your own team) are skipped; names shorter than five
    characters are too likely to match ordinary words."""
    try:
        path = subprocess.run(["git", "config", "--get", "founder-crm.privateDb"], cwd=ROOT,
                              capture_output=True, text=True).stdout.strip()
    except OSError:
        return None
    if not path:
        return None
    import sqlite3

    if not Path(path).is_file():
        raise SystemExit(f"founder-crm.privateDb is set but {path} does not exist.")
    c = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    rows = c.execute(
        "SELECT a.name FROM accounts a WHERE a.lifecycle<>'internal'"
        " UNION SELECT p.name FROM contacts p JOIN accounts a ON a.id=p.account_id WHERE a.lifecycle<>'internal'"
        " UNION SELECT p.email FROM contacts p JOIN accounts a ON a.id=p.account_id WHERE a.lifecycle<>'internal' AND p.email IS NOT NULL"
    ).fetchall()
    c.close()
    terms = sorted({r[0].strip() for r in rows if r[0] and len(r[0].strip()) >= 5})
    if not terms:
        return None
    return re.compile(
        r"(?<![\w@.])(?:" + "|".join(re.escape(t) for t in terms) + r")(?![\w@])", re.IGNORECASE
    )


def check():
    errors = []
    terms = private_terms()
    if terms:
        PATTERNS["record from your private CRM"] = terms
    if len(FILES) != len(set(FILES)):
        errors.append("Duplicate entries in source allowlist.")
    for name in FILES:
        path = ROOT / name
        parts = Path(name).parts
        if (
            not path.is_file()
            or path.is_symlink()
            or not path.resolve().is_relative_to(ROOT)
        ):
            errors.append(f"Not a regular source file: {name}")
            continue
        if any(
            p in {"data", ".venv", ".git", "__pycache__"} for p in parts
        ) or path.suffix in {".db", ".sqlite", ".sqlite3", ".pyc"}:
            errors.append(f"Runtime/private file in allowlist: {name}")
        if Path(name).name in {".env", ".mcp.json", "gmail-token.json"}:
            errors.append(f"Active configuration in allowlist: {name}")
        if path.suffix.lower() in {".png", ".jpg", ".jpeg"}:
            continue
        text = path.read_text()
        for label, pattern in PATTERNS.items():
            if pattern.search(text):
                errors.append(f"Possible {label}: {name}")
    if errors:
        raise SystemExit("\n".join(errors))
    print(
        f"Checked {len(FILES)} allowlisted public files; no runtime data, active configuration or recognised secret patterns found."
    )


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def check_tracked():
    # Bind the scan to what Git will publish, not an uncommitted working copy.
    if subprocess.run(["git", "diff", "--quiet", "HEAD", "--"], cwd=ROOT).returncode:
        raise SystemExit("Commit tracked changes before the push check.")
    tracked = set(git("ls-files").decode().splitlines())
    if tracked != set(FILES):
        raise SystemExit("Tracked files differ from the public allowlist: " + ", ".join(sorted(tracked ^ set(FILES))))


def check_outgoing(updates):
    # Inspect every new/changed blob in outgoing commits, including a private file
    # added and removed before HEAD. Report paths only, never matching contents.
    for line in updates.splitlines():
        local_ref, local_sha, remote_ref, remote_sha = line.split()
        if set(local_sha) == {"0"}:
            continue
        revisions = [local_sha]
        if set(remote_sha) != {"0"}:
            revisions.append("^" + remote_sha)
        for commit in git("rev-list", *revisions).decode().splitlines():
            names = git("diff-tree", "--root", "--no-commit-id", "-r", "--diff-filter=ACMRT", "--name-only", "-z", commit).decode().split("\0")
            for name in filter(None, names):
                if name not in FILES:
                    raise SystemExit("Push refused: unreviewed file in outgoing history: " + name)
                if Path(name).suffix.lower() in {".png", ".jpg", ".jpeg"}:
                    continue
                content = git("show", commit + ":" + name).decode()
                for label, pattern in PATTERNS.items():
                    if pattern.search(content):
                        raise SystemExit("Push refused: possible " + label + " in " + name)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tracked", action="store_true", help="Require a clean tracked tree matching the release allowlist")
    parser.add_argument("--pre-push", action="store_true", help="Also check outgoing Git history supplied by the pre-push hook")
    args = parser.parse_args()
    if args.tracked or args.pre_push:
        check_tracked()
    check()
    if args.pre_push:
        check_outgoing(sys.stdin.read())
