# 07 — Costs and Billing

> **Who this is for:** beginner developers and non-technical readers.
> **Repository stamp:** base commit `ba8c7c0` · branch `docs/update-documentation-2026-10-11` · dated 2026-10-11 · no uncommitted changes when the docs were written.
> Back to [Documentation index](README.md)

## Contents

- [What can cost money](#what-can-cost-money)
- [What the code does to contain cost](#what-the-code-does-to-contain-cost)
- [Where to check the actual bill](#where-to-check-the-actual-bill)

## What can cost money

This project's cost surface is small but real — three metered services:

| Service | What runs on it | Billing unit |
|---|---|---|
| GitHub Actions | `poll.yml` every 30 min (~48 runs/day) | Minutes — **private repos bill against the account's monthly Actions minutes**; Linux minutes count at the standard rate |
| Cloud Run | `novels-worker` job, on-demand only | vCPU/memory-seconds per execution |
| Firestore (`mw-novels`) | All cloud data | Reads/writes/storage — project is on the **Blaze** (pay-as-you-go) plan |

Local mode costs nothing beyond your own hardware and bandwidth.

## What the code does to contain cost

Cost controls are built into the pipeline, not bolted on:

- **Time budgets everywhere** — `POLL_RUN_BUDGET_S` (1260 s) < the workflow's
  25-minute timeout; `RSS_TIME_BUDGET_S` (300 s) and `QUEUE_TIME_BUDGET_S`
  (1200 s) bound each phase; `WORKER_RUN_BUDGET_S` (3300 s) < the Cloud Run
  job's 3600 s limit. A run can never spin indefinitely.
- **Monthly execution cap** — `WORKER_MAX_MONTHLY_RUNS` /
  `claim_worker_run` makes the worker refuse runs past a configured count,
  so a stuck site trigger can't spin the meter.
- **Off-peak schedule** — cron `7,37 * * * *` hits minutes other crons
  don't, reducing queue delay (a reliability trick, not a cost one).
- **Minimal CI image** — `requirements-poller.txt` + the Playwright
  container with browsers baked in avoids per-run install/download time,
  keeping each billed minute shorter.
- **Insert-if-absent** — re-runs don't duplicate writes, keeping Firestore
  write counts proportional to real new data.

*Inferred:* per-run cost is a few cents at most — ~4 billed Actions minutes
per poll (~1400/month) and seconds of Cloud Run per worker execution — but
exact numbers depend on account pricing tier and were not measured.

**Published pricing** (official pages, checked 2026-10-11):

- GitHub Actions billing: <https://docs.github.com/en/billing/concepts/product-billing/github-actions>
  — private-repo minutes draw from the account's included quota, then a
  per-minute rate.
- Cloud Run pricing: <https://cloud.google.com/run/pricing> — vCPU-seconds
  and GiB-seconds; there is a monthly free tier the worker cap is sized
  against (see `deploy_worker.sh` comments).
- Firestore pricing: <https://cloud.google.com/firestore/pricing> — per
  read/write/delete plus stored data; Blaze = pay-as-you-go.

## Where to check the actual bill

- **GitHub**: Settings → Billing and licensing → Actions minutes (per-account).
- **Google Cloud / Firebase**: console.firebase.google.com → project
  `mw-novels` → Usage and billing → Blaze plan details; Cloud Run usage is in
  console.cloud.google.com under the same project.
- **Firestore rules reminder**: `firestore.rules` is public-read — reads are
  metered, so an exposed hot page on the site can grow read costs.
