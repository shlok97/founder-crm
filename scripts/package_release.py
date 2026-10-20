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
    ".githooks/pre-push",
    "loop_crm/__init__.py",
    "loop_crm/__main__.py",
    "loop_crm/core.py",
    "loop_crm/schema.sql",
    "loop_crm/demo.py",
    "loop_crm/judge.py",
    "loop_crm/integrations.py",
    "loop_crm/web.py",
    "loop_crm/mcp_server.py",
    "loop_crm/static/index.html",
    "loop_crm/static/style.css",
    "loop_crm/static/app.js",
    ".claude/skills/crm-daily-review/SKILL.md",
    ".claude/skills/crm-capture-conversation/SKILL.md",
    ".claude/skills/crm-review-proposal/SKILL.md",
    "docs/architecture.md",
    "docs/integrations.md",
    "docs/personalise.md",
    "docs/personalisation-test.md",
    "docs/examples/agency-owner.patch",
    "docs/verification.md",
    "docs/release-review.md",
    "docs/maintaining.md",
    "docs/images/dashboard.jpg",
    "docs/images/architecture.svg",
    "docs/images/architecture.png",
    "docs/brand/altys-logo.svg",
    "docs/brand/README.md",
    "docs/brand/github-social.jpg",
    "docs/brand/loop-crm-indian-editorial.png",
    "tests/test_workflow.py",
    "tests/test_http.py",
    "tests/test_mcp.py",
    "tests/test_integrations.py",
    "tests/test_v2.py",
    "scripts/package_release.py",
    "scripts/start.py",
    "scripts/check_public_files.py",
]


def package():
    dest = ROOT / "dist"
    dest.mkdir(exist_ok=True)
    archive = dest / "loop-crm-0.4.0.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        for name in sorted(FILES):
            source = ROOT / name
            if source.is_symlink() or not source.is_file():
                raise RuntimeError(f"Expected a regular release file: {name}")
            info = zipfile.ZipInfo(
                "loop-crm/" + name, date_time=(2026, 10, 19, 0, 0, 0)
            )
            info.compress_type = zipfile.ZIP_DEFLATED
            mode = 0o100755 if source.stat().st_mode & 0o111 else 0o100644
            info.external_attr = mode << 16
            z.writestr(info, source.read_bytes())
    checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
    (dest / "SHA256SUMS").write_text(f"{checksum}  {archive.name}\n")
    return archive, checksum


if __name__ == "__main__":
    archive, checksum = package()
    print(archive)
    print(checksum)
