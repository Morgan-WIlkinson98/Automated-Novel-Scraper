# Contributing to Novel Scraper

> **Who this is for:** anyone proposing a change to this repository.
> **Repository stamp:** base commit `ba8c7c0` · branch `docs/update-documentation-2026-10-11` · dated 2026-10-11.
> Previous version: [docs/archive/2026-10-10_CONTRIBUTING.md](docs/archive/2026-10-10_CONTRIBUTING.md)

This is a personal project, but contributions follow a fixed workflow so the
owner can review without reconstructing context.

## Workflow — the short version

1. **`git fetch --all --prune`**, then branch from latest `main`. Never commit
   to `main` directly.
2. **Open a GitHub issue first** describing the work — every branch maps to
   one. Use the bug-report or feature-request template.
3. Branch name: `feature/<short-description>` (or `fix/<desc>` for a bug).
4. Make the change. Keep it small and focused — one feature or fix per branch.
5. **Open a draft PR to `main`** with `Closes #<issue>` in the body; mark
   ready only when verified. Link the PR back on the issue.
6. The owner handles the merge.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate   # Python >= 3.10
pip install -r requirements.txt
python -m playwright install chromium
cp core/config.example.py config.py   # fill in your own credentials — never commit it
```

Full instructions: [docs/02-setup-and-quickstart.md](docs/02-setup-and-quickstart.md).

## Rules that matter here

- **Secrets**: `config.py`, cookies, service-account JSON — never commit, never
  paste into issues/PRs. Actions secrets are `NU_RSS_FEED_URL`, `NU_COOKIES`,
  `FIREBASE_SERVICE_ACCOUNT_JSON`.
- **Never put a backslash inside an f-string expression** (`f"{x.replace('\n',' ')}"`
  is a SyntaxError on <3.12). Assign first, interpolate second.
- **Packages**: don't add or upgrade a dependency without vetting it against
  [docs/PACKAGE-SECURITY.md](docs/PACKAGE-SECURITY.md) and getting approval —
  prefer building in-repo first.
- **Database safety**: back up `chapters.db` before any schema change; deletes
  of user data need explicit approval (see `AGENTS.md` data-safety rules).
- **Docs in the same PR**: if you change behavior, update the matching file in
  `docs/` in the same PR — stale docs are a bug.
- **Politeness is a feature**: keep `robots.txt` checks and rate limits intact;
  don't add code that bypasses them.

## Verifying your change

There is no test suite. Before marking a PR ready:

```bash
python -m compileall . -q                              # syntax
python -c "import main, web_ui, poller, queue_worker"  # imports
python web_ui.py                                        # UI boots on :6110
```

More paths: [docs/06-testing-and-debugging.md](docs/06-testing-and-debugging.md).

## PR description must cover

Summary · why (link the issue) · approach and alternatives · how to test
(numbered steps) · review focus · checklist. The PR template
(`.github/pull_request_template.md`) walks you through it.

## Code conventions

- Package imports, not flat-module ones: `from data.storage import ...`,
  `from rss.rss_watcher import ...`.
- Settings go through `core/settings.py` (env → `config.py` → defaults) —
  never read `config.py` directly from app code.
- New scraping code routes through `scraping/politeness.py`.
- Match the existing style; keep functions focused.

## Reporting issues

Use the templates in `.github/ISSUE_TEMPLATE/`. For bugs: what you did, what
you expected, what happened, logs. Never include credentials, cookies, or
your private RSS URL.
