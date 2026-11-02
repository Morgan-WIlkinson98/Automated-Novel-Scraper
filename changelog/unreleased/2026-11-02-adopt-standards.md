# Adopt dev/release workflow and changelog standard

- **Status:** Pending
- **Type:** Change
- **Issue:** _added once the issue is created_
- **Branch:** `feature/adopt-standards`

## What changed
Feature branches now start from `dev` and merge into it without a PR; `dev` reaches `main` only through a `release/<yyyy-mm-dd>` branch and its release PR. Adds `CHANGELOG.md`, `changelog/unreleased/` for Pending entries, and a Release section in the deployment checklist.

## Why
Aligns the repository with the global workflow standard. Changes on `dev` stay Pending until a release carries them to `main`.
