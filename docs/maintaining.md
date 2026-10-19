# Publishing changes

Maintainers publish through normal Git over HTTPS. Browser uploads were used for
the initial import; they are not the update workflow.

Sign in once with GitHub CLI as an account with write access to this repository:

```sh
gh auth login --hostname github.com --git-protocol https --web
gh auth setup-git
git config core.hooksPath .githooks
```

GitHub CLI stores credentials in the operating system keyring when available.
Do not put a token in a remote URL, source file, MCP config or shell history.

For an update, start from the current branch, make the change, run the checks, and
stage only the intended source files. Add new public files to `FILES` in
`scripts/package_release.py` deliberately.

```sh
python -m unittest discover -s tests -v
node --check founder_crm/static/app.js
python scripts/check_public_files.py
git diff --check
# git add <explicit source paths>
git commit -m "Describe the change"
git fetch origin
git push --dry-run origin main
git push origin main
gh run list --limit 1
```

The pre-push hook requires a clean tracked tree matching the public allowlist. It
also scans changed blobs in every outgoing commit, so adding private data and
deleting it in a later commit does not make that history publishable. It checks
common credential patterns; it is not a complete secret or privacy detector.
Review your diff and keep runtime data under ignored `data/`.

GitHub Actions installs the actual package after creating demo data, checks its
schema/static resources, runs the base suite from outside the checkout, and tests
the browser JavaScript. Check that the run is green before announcing an
update. Never force-push to work around an unexpected remote change.

The source ZIP is optional: `python scripts/package_release.py`. Its allowlist is
separate from Python packaging; the wheel contains only `founder_crm` and its
runtime resources. Databases and credentials belong in neither archive.
