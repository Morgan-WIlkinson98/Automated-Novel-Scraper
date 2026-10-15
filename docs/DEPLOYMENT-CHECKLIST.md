# Deployment Checklist

Run this **after every merge to `main`** that touches the pipeline
(`poller.py`, `queue_worker.py`, extractors, `requirements-poller.txt`,
`poll.yml`), after rotating any GitHub secret, and after redeploying the
`novels-worker` Cloud Run Job. This repo's "deploy" is the next
scheduled run — code ships when `poll.yml` executes, so a green PR merge
means nothing until a run proves it.

The failure mode this exists for: silent staleness. Secrets can be
present-but-emptied, cookies can expire, and NU's Cloudflare challenge
can start bouncing headless runs — each one leaves the site looking fine
while data stops flowing.

## 1. Last poller run is green

```bash
gh run list --workflow=poll.yml --limit 5
```

- [ ] Latest scheduled run (`schedule` event) shows `completed success`
- [ ] If the newest code hasn't run yet, force one:
  `gh workflow run poll.yml` and watch it green
- [ ] Read the log tail (`gh run view <id> --log`) for the summary line —
  "processed N" with N≥0 and no fatal exceptions

## 2. Secrets are present and fresh

```bash
gh secret list
```

- [ ] `NU_RSS_FEED_URL`, `FIREBASE_SERVICE_ACCOUNT_JSON`, `NU_COOKIES`
  all listed
- [ ] `NU_COOKIES` — NU sessions expire; if runs show challenge/login
  walls, re-export cookies and update the secret
- [ ] `FIREBASE_SERVICE_ACCOUNT_JSON` — same key the site uses as
  `NOVELS_SA_JSON`; if the key is rotated, update BOTH (site side via
  `tools/pages-secrets.py` in the morganwilkinson.com repo)

## 3. Firestore write path is alive

The site reads `mw-novels` Firestore — verify data is actually moving:

- [ ] Novels page Backend card (`morganwilkinson.com/apps/novels`, or
  `/apps/novels/api/runstatus`) shows "Last run … ago" within ~40 min
  and no rising error strings
- [ ] A novel's latest-update row is newer than the last confirmed
  release — i.e. writes land, not just runs completing
- [ ] Firestore console (project `mw-novels`) shows `novels/*` docs with
  fresh `updatedAt`-style fields if the card looks stale

## 4. Backfill queue end-to-end

- [ ] From the site's series page, press **fetch missing chapters** —
  expect `ok`, not "request endpoint not configured" (that error is
  site-side `NOVELS_SA_JSON`, fixed in the morganwilkinson.com repo)
- [ ] `novels_requests/{slug}` in Firestore moves `pending → done` and
  chapters appear in the reader — proves `novels-worker` Cloud Run Job
  executed and could write
- [ ] Fallback path still works if touched:
  `gh workflow run poll.yml -f slug=<slug>` processes the queue doc

## 5. Cloud Run Job health (when changed)

Only needed if `tools/deploy_worker.sh`, the Docker image, or worker
code changed:

- [ ] `bash tools/deploy_worker.sh` completed (image pushed, job updated)
- [ ] Latest execution succeeded — GCP console → Cloud Run →
  `novels-worker` → Executions (project `mw-novels`, `us-central1`)
- [ ] Monthly run-cap ledger sane (`WORKER_MAX_MONTHLY_RUNS` doc in
  Firestore — the job refuses to run past it, so a "stuck" queue may
  just be a spent budget)

## 6. Scraping is actually scraping

- [ ] Run log shows chapter fetches succeeding — not a wall of
  "Cloudflare challenge blocked" for *every* host (some blocks are
  normal; all-blocks means cookies/headers need attention)
- [ ] Mirror fallbacks (wuxiaworld.eu → novelfull.net → novellunar.com)
  still resolving for backfill hosts

## 7. Local/Docker mode (when touched)

If `main.py`, `web_ui.py`, `docker-compose.yml`, or Dockerfile changed:

- [ ] `python3 -m py_compile` on touched files — no syntax errors
  (mind the f-string backslash rule)
- [ ] `docker compose config` parses; `start.py` boots the UI on :6110

## 8. Paperwork gates

- [ ] Docs synced in the same PR — `README.md`, `docs/*` match reality
- [ ] Site docs updated if the contract changed (Firestore schema,
  `novels_requests` fields, endpoints the site calls — those live in
  the morganwilkinson.com repo and must not drift)

## If something fails

- Whole pipeline dark → check `poll.yml` run logs first, then GitHub
  secrets presence, then NU cookies freshness (most common rot)
- Queue stuck `pending` with green poll runs → worker cap ledger or
  Cloud Run job failure; the GitHub dispatch fallback covers it
- Site-side errors (`503` on the request endpoint) → that's the
  orchestrator repo, not this one
