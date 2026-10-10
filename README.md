# Novel Scraper

Watches a private NovelUpdates RSS feed for new chapter releases, follows each
release link to the site actually hosting the chapter, extracts the text, and
stores it — locally in SQLite, or in Firestore when running as a scheduled
cloud pipeline feeding the Novels app on morganwilkinson.com.

> **Who this is for:** beginner developers and non-technical readers.
> **Repository stamp:** base commit `217431f` · branch `feature/update-documentation-2026-10-10` · dated 2026-10-10.
> Previous version: [docs/archive/2026-10-10_README-root.md](docs/archive/2026-10-10_README-root.md)

## How it works

```text
RSS feed → resolve /extnu/ link (browser fallback) → extract text
   (trafilatura → readability → rendered HTML → site override) → store
                                                    ↑
                              politeness layer wraps every HTTP call
                              (robots.txt + per-domain rate limit)
```

A request queue handles backfills ("fetch all missing chapters"), trying three
mirror sites — wuxiaworld.eu → novelfull.net → novellunar.com — before the
original linked host.

## Two ways to run it

| | Local | Cloud |
|---|---|---|
| Start | `python start.py` (UI + scraper) or `docker-compose up -d` | GitHub Actions every 30 min (`poll.yml`) + on-demand Cloud Run Job |
| Entry | `main.py`, `web_ui.py` (port 6110) | `poller.py`, `queue_worker.py` |
| Storage | `chapters.db`, `seen_entries.db` | Firestore (`mw-novels` project) |

## Quickstart

```bash
git clone https://github.com/Morgan-Wilkinson/Automated-Novel-Scraper.git
cd Automated-Novel-Scraper
python -m venv .venv && source .venv/bin/activate   # Python ≥ 3.10
pip install -r requirements.txt
python -m playwright install chromium                # + xvfb on Linux
cp core/config.example.py config.py                  # then fill in credentials
python start.py                                      # UI at http://localhost:6110
```

`config.py` is gitignored — never commit it. Details:
[docs/02-setup-and-quickstart.md](docs/02-setup-and-quickstart.md).

## Documentation

The full documentation set lives in **[docs/](docs/README.md)**:

| Doc | Covers |
|---|---|
| [01 — Overview and architecture](docs/01-overview-and-architecture.md) | System design, pipeline diagrams, decisions and why |
| [02 — Setup and quickstart](docs/02-setup-and-quickstart.md) | Local, Docker, and cloud setup step by step |
| [03 — Project structure](docs/03-project-structure.md) | What every file is for |
| [04 — Core modules and APIs](docs/04-core-modules-and-apis.md) | Functions and HTTP endpoints |
| [05 — Configuration and services](docs/05-configuration-and-services.md) | Every setting and external service |
| [06 — Testing and debugging](docs/06-testing-and-debugging.md) | Verification and common problems |
| [07 — Costs and billing](docs/07-costs-and-billing.md) | Cloud cost model and controls |
| [08 — Known limitations and enhancements](docs/08-known-limitations-and-enhancements.md) | Weak spots + tracked issues |
| [Glossary](docs/glossary.md) · [References](docs/references.md) | Terms and links |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Short version: fetch, open an issue,
branch `feature/<desc>` off `main`, draft PR — never commit to `main`.

## License

Personal project; use at your own discretion. Be a polite client of the sites
you read from — the politeness layer exists so the defaults already are.
