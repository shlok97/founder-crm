"""Create a source-only release archive from reviewed, explicit file names."""

from pathlib import Path
import hashlib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    "README.md",
    "LICENSE",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "AGENTS.md",
    "CLAUDE.md",
    "pyproject.toml",
    ".gitignore",
    ".gitattributes",
    ".env.example",
    ".mcp.json.example",
    ".github/workflows/checks.yml",
    "founder_crm/__init__.py",
    "founder_crm/__main__.py",
    "founder_crm/core.py",
    "founder_crm/schema.sql",
    "founder_crm/demo.py",
    "founder_crm/judge.py",
    "founder_crm/integrations.py",
    "founder_crm/web.py",
    "founder_crm/mcp_server.py",
    "founder_crm/static/index.html",
    "founder_crm/static/style.css",
    "founder_crm/static/app.js",
    ".claude/skills/crm-daily-review/SKILL.md",
    ".claude/skills/crm-capture-conversation/SKILL.md",
    ".claude/skills/crm-review-proposal/SKILL.md",
    "docs/architecture.md",
    "docs/integrations.md",
    "docs/personalise.md",
    "docs/personalisation-test.md",
    "docs/examples/agency-owner.patch",
    "docs/verification.md",
    "docs/images/dashboard.jpg",
    "docs/images/architecture.svg",
    "docs/images/architecture.png",
    "docs/brand/altys-logo.svg",
    "docs/brand/github-social.svg",
    "docs/brand/github-social.png",
    "tests/test_workflow.py",
    "tests/test_http.py",
    "tests/test_mcp.py",
    "scripts/package_release.py",
    "scripts/start.py",
    "scripts/check_public_files.py",
]


def package():
    dest = ROOT / "dist"
    dest.mkdir(exist_ok=True)
    archive = dest / "founder-crm-0.1.0.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        for name in sorted(FILES):
            source = ROOT / name
            if source.is_symlink() or not source.is_file():
                raise RuntimeError(f"Expected a regular release file: {name}")
            info = zipfile.ZipInfo(
                "founder-crm/" + name, date_time=(2026, 10, 19, 0, 0, 0)
            )
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            z.writestr(info, source.read_bytes())
    checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
    (dest / "SHA256SUMS").write_text(f"{checksum}  {archive.name}\n")
    return archive, checksum


if __name__ == "__main__":
    archive, checksum = package()
    print(archive)
    print(checksum)
