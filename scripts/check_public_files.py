"""Check the exact source-release allowlist; never inspect private runtime data."""

from pathlib import Path
import re
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


def check():
    errors = []
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


if __name__ == "__main__":
    check()
