# Adopt branch workflow and changelog standard

- **Status:** Pending
- **Type:** Change
- **Issue:** _added once the issue is created_
- **Branch:** `feature/adopt-standards`

## What changed
Feature branches start from `main` and ship to `main` by a PR from the feature branch, or several together from a `release/<yyyy-mm-dd>` branch cut from `main`. `dev` becomes a testing branch that features merge into without a PR and that is never merged into `main`. Adds `CHANGELOG.md`, `changelog/unreleased/` for Pending entries, and a Ship to `main` section in the deployment checklist, including the post-merge `dev` sync.

## Why
Aligns the repository with the global workflow standard. Changes stay Pending until the PR that carries them is merged to `main`.
