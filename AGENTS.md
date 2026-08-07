# Automated Novel Scraper Project Rules

## Global Skills

This repository uses the following global skills for standardized development:

- **development-workflow**: Follow for all branch management, issue tracking, and PR processes
- **repo-setup**: Use for setting up similar rules in other repositories

Invoke these skills with `/development-workflow` or `/repo-setup` in any session.

## Repository-Specific Rules

See `.devin/rules/REPOSITORY_RULES.md` for detailed repository-specific rules.

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

When working on this repository:
1. Create GitHub issue for each bug/feature
2. Create feature branch from main: `feature/ISSUE-123-fix-description`
3. Implement changes following Python best practices
4. Test thoroughly before creating PR
5. Create draft PR to main linking to issue
6. Request user testing and confirmation
7. Create final backup after user confirmation
8. Merge to dev for further testing
9. User handles main merge manually