# Automated Novel Scraper Project Rules

## Global Skills

This repository uses the following global skills for standardized development:

- **development-workflow**: Follow for all branch management, issue tracking, and PR processes
- **repo-setup**: Use for setting up similar rules in other repositories

Invoke these skills with `/development-workflow` or `/repo-setup` in any session.

## Repository-Specific Rules

See `.devin/rules/REPOSITORY_RULES.md` for detailed repository-specific rules.

## Shared Rules — morganwilkinson.com App Family

Common rules for every repo hosting an app under morganwilkinson.com
(the site/orchestrator repo, this repo, 3d-printer-workshop, ...).
Keep them in sync across repos — when they change in one, propagate.

### App isolation (CRITICAL)

Apps hosted under morganwilkinson.com are independent of each other —
this app must never share databases, rules files, secrets, or other
backend infrastructure with other apps (e.g. the 3d-printer-workshop
repo). This app owns its Firebase project (`mw-novels`)
end to end. The only cross-app touchpoint allowed is the orchestrator
repo (morganwilkinson.com), which hosts the hub and Access config.

### Documentation sync (required)

Any change to code, config, infrastructure, or deploy behavior MUST
update the docs in the **same PR** so they always match the real state:

- `README.md` — setup, stack, features
- `AGENTS.md` — if rules/processes changed
- Any other docs the change touches

Never leave docs describing retired behavior, dead URLs, or removed
infrastructure. If you notice stale docs while working, fix them.

### Secrets discipline

Secrets live only in GitHub Actions secrets — never in source,
`config.py`, tests, or other committed files. This repo's secrets:
`NU_RSS_FEED_URL`, `FIREBASE_SERVICE_ACCOUNT_JSON`, `NU_COOKIES`.

### Branch & PR hygiene

- Fetch before branching — `git fetch --all --prune`, then base off the
  latest `main`; local branches may be stale or already merged
- Issue first — create a GitHub issue for the work before branching;
  every feature branch maps to an issue
- Feature branches off `main`; never commit directly to `main` or `dev`
- Draft PR first; mark ready only when verified
- PR body must include: what changed and why, breaking changes or
  migration notes, numbered how-to-test steps a reviewer can follow,
  and testing evidence

### Data safety — deletes (CRITICAL)

Any delete of user data — a UI action, a script or migration, or an
agent-run command — must guarantee no important data is lost:

- **Say exactly what will be deleted and get explicit approval first**
  — which records, how many, and side effects like orphaned
  references. UI confirm dialogs must describe what is actually
  removed; never claim related records are deleted when they aren't.
- **Compound create-then-delete operations must be atomic or strictly
  ordered.** When an action creates a replacement and removes the
  original (convert, migrate, move), the delete must never run unless
  the create succeeded — use a transaction/batch where the store
  supports one, or gate the delete on the write's success. A failed
  operation leaves the original data untouched.
- **Check dependents before deleting** a record other data references —
  preserve what the references need (snapshot metadata, keep ids,
  migrate references) or block the delete.
- **Prefer recoverable deletes** — soft-delete/archive flags, backups,
  export-before-migration — wherever practical.

## Package & Dependency Installation Security

**Core rule: never install, upgrade, or add a dependency without completing
the vetting checklist.** `pip install` is remote code execution, not a
harmless convenience. The full policy lives in
[docs/PACKAGE-SECURITY.md](docs/PACKAGE-SECURITY.md); summary:

- **Necessity / build-first** — always try building the functionality
  in-repo first (standard library, an existing dependency, or a few
  lines of code). Before adding any package, weigh build-yourself vs.
  third-party — implementation effort, maintenance burden, supply-chain
  surface, features gained — present the comparison with a
  recommendation, and get the user's approval for the path. Reject
  disproportionate dependency trees.
- **Authenticity** — verify the package name character-by-character against
  the project's official docs/repo; confirm the PyPI page links back to the
  trusted repository; watch for typosquats and lookalike names.
- **Reputation & maintenance** — real adoption (downloads, dependents,
  contributors), commits and a release within the last 12 months, preferably
  multiple maintainers and a `SECURITY.md`.
- **Vulnerability status** — the exact version has no unpatched Critical/High
  findings in OSV / deps.dev and is not in the OSV malicious-packages set.
- **Freshness** — prefer versions published 7–30+ days ago; brand-new
  releases are the highest-risk moment for supply-chain attacks.
- **Install-script scrutiny** — check for `setup.py`/build hooks that run or
  fetch code at install time; prefer wheels (`--only-binary :all:`).
- **Exact pinning + lockfile** — pin `==` versions in `requirements*.txt` /
  `pyproject.toml`; prefer `pip install --require-hashes`.
- **Post-install audit** — run `pip-audit`, review the transitive tree with
  `pipdeptree` / deps.dev, commit the updated manifests, re-run tests.
- **Agents**: report a short vetting summary and get approval before any
  install not already in the manifests; PyPI only — no alternate indexes,
  no `curl | sh`, no `--no-deps` side installs.

## Python Code Quality Rules

### F-String Syntax (CRITICAL)
- **NEVER use backslashes in f-string expressions** - this causes SyntaxError
- Move string replacement operations outside f-strings when needed
- Example of ERROR: `f"{text.replace('\n', '<br/>')}"` 
- Example of CORRECT: `processed = text.replace('\n', '<br/>'); f"{processed}"`

### Import Structure
- After module reorganization, use proper package imports
- Import from parent packages when needed: `from data.export import get_statistics`
- Avoid circular imports between modules

### Error Handling
- Database operations need proper error handling
- File operations should have try/except blocks
- Network requests need timeout handling
- Log errors appropriately for debugging

## Data Safety Rules

### Database Operations
- **ALWAYS backup** database (chapters.db) before schema changes
- Use transactions for multi-step database operations
- Test database migrations on copy first
- Database contains user's reading progress - protect it

### Configuration Files
- config.py contains sensitive RSS credentials - protect appropriately
- Don't commit config.py with real credentials
- Use config.example.py as template

### Export Functionality
- EPUB generation requires proper HTML escaping
- Handle missing chapters gracefully
- Validate export file paths before writing
- Large exports need memory management

## Testing Requirements

Before any PR completion:
- [ ] Python syntax is valid (no f-string errors)
- [ ] Import structure is correct
- [ ] Scraper can handle basic RSS feeds
- [ ] Web UI loads without errors
- [ ] Export functionality works
- [ ] Database operations don't corrupt data
- [ ] RSS authentication works if configured

## Development Workflow

- Every new feature/change must be developed on a feature branch named
  `feature/<short-description-or-issue>` created from `main` — never commit
  directly to `main`.
- Every feature branch must get a pull request whose description is genuinely
  useful to a reviewer — full enough that they don't have to reconstruct
  context from the diff. Include:

  - **Summary** — what changed in 1-3 bullets describing behavior, not filenames
  - **Why** — what it addresses/fixes and why; the most important part. Link
    the issue it closes when one exists
  - **Approach** — key implementation decisions and alternatives rejected
    (when non-obvious)
  - **How to test** — exact steps or commands and the expected result
  - **Review focus** — point reviewers at risky, subtle, or uncertain parts
    when relevant
  - **Screenshots/output** — before/after for UI changes
  - **Checklist** — tests added/updated, docs updated, migrations/rollback
    considered, security/permissions reviewed

  Items that don't apply may be dropped rather than left as empty ritual.

When working on this repository:
1. Fetch the latest branches (`git fetch --all --prune`), create a
   GitHub issue for the work, then create a feature branch from main:
   `feature/short-description`
2. Implement changes following Python best practices
3. Test thoroughly before creating PR
4. Create draft PR to main with:
   - Assignee: repository owner/user
   - Reviewer: repository owner/user
5. Request user testing and confirmation
6. Create final backup after user confirmation
7. Merge to dev for further testing
8. User handles main merge manually
