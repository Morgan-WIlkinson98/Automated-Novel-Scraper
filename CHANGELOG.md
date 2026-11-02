# Changelog

Changes merged to `main`, newest first. Changes still in progress are in
[changelog/unreleased/](changelog/unreleased/) with status Pending.

**Archives:** none yet

## 2026

### 2026-11-02 — Adopt branch workflow and changelog standard

- **Status:** Approved
- **Type:** Change
- **Issue:** [#69](https://github.com/Morgan-WIlkinson98/Automated-Novel-Scraper/issues/69)
- **Pull request:** [#<n>](https://github.com/Morgan-WIlkinson98/Automated-Novel-Scraper/pull/<n>) · [Files changed](https://github.com/Morgan-WIlkinson98/Automated-Novel-Scraper/pull/<n>/files)

**What changed:** Feature branches start from `main` and ship to `main` by a PR from the feature branch, or several together from a `release/<yyyy-mm-dd>` branch cut from `main`. `dev` becomes a testing branch that features merge into without a PR and that is never merged into `main`. Adds `CHANGELOG.md`, `changelog/unreleased/` for Pending entries, and a Ship to `main` section in the deployment checklist, including the post-merge `dev` sync.

**Why:** Aligns the repository with the global workflow standard. Changes stay Pending until the PR that carries them is merged to `main`.

