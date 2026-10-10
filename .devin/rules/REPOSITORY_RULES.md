# Automated Novel Scraper Repository Rules

## Repository Type
python-app - Python-based novel RSS feed scraper with web UI

## Repository-Specific Rules

### Development Workflow
Follow the global development-workflow skill for all changes.

**PR Requirements**:
- PR must be in draft state
- PR must have assignee (repository owner/user)
- PR must have reviewer (repository owner/user)

### Backup Requirements
- **CRITICAL**: Always backup data directory before any data structure changes
- Backup configuration files (config.py) before major configuration changes
- Backup export.py before EPUB export logic changes
- Database (chapters.db) contains important user data - backup before schema changes

### Python Code Quality
- **CRITICAL**: No backslashes in f-string expressions (causes SyntaxError)
- Move string operations outside f-strings when needed
- Follow PEP 8 style guidelines
- Use type hints for function signatures
- Add docstrings for complex functions

### Service-Specific Rules

#### Data/Export Module
- f-string expressions cannot contain backslashes
- String replacement operations must be done outside f-strings
- EPUB generation requires proper HTML escaping
- File operations need proper error handling

#### Web UI
- Flask app runs on port 6110 by default
- Web UI requires proper import structure for data module
- Export functions must handle missing data gracefully
- Statistics queries should be optimized

#### Scraper Module
- Browser automation requires proper timeout handling
- Cloudflare challenges need user notification
- RSS authentication credentials should be in config.py
- Rate limiting is important for politeness

### Testing Requirements
Before any PR completion:
- [ ] Python syntax is valid (no f-string errors)
- [ ] Import structure is correct
- [ ] Scraper can handle basic RSS feeds
- [ ] Web UI loads without errors
- [ ] Export functionality works
- [ ] Database operations don't corrupt data

### Deployment Requirements
- Docker container rebuild required for code changes
- Configuration changes may require container restart
- Data directory mounts must be preserved
- Database migrations need backup before execution

### Common Issues to Check
- f-string syntax errors (backslash in expressions)
- Import path issues after module reorganization
- Database schema changes
- Browser compatibility for scraping
- RSS feed authentication failures

### Infrastructure Facts (verify in docs before assuming)
- `mw-novels` Firebase project is on the **Blaze plan** — billing enabled
  on account `016C4E-045E5A-AED2E2`. Firestore, Cloud Run, and other paid
  APIs can bill on overage; nothing silently upgrades anything.
- Free-tier guardrails for the Cloud Run worker: `novels_meta/worker_usage`
  monthly execution ledger + `WORKER_MAX_MONTHLY_RUNS` cap.
- Always read the repo docs/rules before answering infrastructure or
  billing-state questions — do not infer project state.
