---
ARCHIVED 2026-10-10 — originally at CONTRIBUTING.md.
Reason: CONTRIBUTING rewritten in place; this copy preserves the previous text (v2 branch workflow, AI-Web-Scraper name, fictional pytest/coverage requirements).
Replaced by: ../../CONTRIBUTING.md
---

# Contributing to AI Novel Web Scraper

Thank you for your interest in contributing to the AI Novel Web Scraper project! This document provides guidelines and instructions for contributing.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Workflow](#development-workflow)
- [Coding Standards](#coding-standards)
- [Testing](#testing)
- [Submitting Changes](#submitting-changes)
- [Reporting Issues](#reporting-issues)

## Code of Conduct

- Be respectful and inclusive
- Provide constructive feedback
- Focus on what is best for the community
- Show empathy towards other community members

## Getting Started

### Prerequisites

- Python 3.8 or higher
- Git
- Virtual environment (recommended)

### Setup Development Environment

1. **Fork and clone the repository**

```bash
git clone https://github.com/YOUR_USERNAME/AI-Web-Scraper.git
cd AI-Web-Scraper
```

2. **Create a virtual environment**

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies**

```bash
pip install -r requirements.txt
```

4. **Install development dependencies** (optional but recommended)

```bash
pip install pytest pytest-cov black flake8 mypy
```

## Development Workflow

### Branch Strategy

- `main` - Stable production code
- `v2` - Current development branch
- Feature branches - `feature/your-feature-name`
- Bugfix branches - `fix/your-bug-fix`

### Making Changes

1. **Create a new branch**

```bash
git checkout -b feature/your-feature-name
```

2. **Make your changes**

3. **Test your changes**

```bash
# Run tests (when available)
pytest

# Run linting
flake8 .
black --check .
mypy .
```

4. **Commit your changes**

```bash
git add .
git commit -m "feat: add your feature description"
```

Follow [Conventional Commits](https://www.conventionalcommits.org/) format:
- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation changes
- `style:` - Code style changes (formatting, etc.)
- `refactor:` - Code refactoring
- `test:` - Adding or updating tests
- `chore:` - Maintenance tasks

5. **Push and create a pull request**

```bash
git push origin feature/your-feature-name
```

Then create a PR on GitHub.

## Coding Standards

### Python Style

- Follow PEP 8 style guide
- Use type hints where appropriate
- Write docstrings for all functions and classes
- Keep functions focused and small
- Use meaningful variable names

### Example Code Style

```python
"""
Module docstring describing the purpose of this module.
"""

from typing import Optional
import requests


def fetch_data(url: str, timeout: int = 15) -> Optional[str]:
    """
    Fetch data from a URL with a timeout.

    Args:
        url: The URL to fetch from
        timeout: Request timeout in seconds

    Returns:
        The response text if successful, None otherwise
    """
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        print(f"Failed to fetch {url}: {e}")
        return None
```

### Documentation

- Update relevant documentation when adding features
- Keep README.md up to date
- Add inline comments for complex logic
- Update API docs when changing interfaces

## Testing

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=.

# Run specific test file
pytest tests/test_extractor.py
```

### Writing Tests

- Write tests for new features
- Maintain test coverage above 80%
- Use descriptive test names
- Test both success and failure cases

## Submitting Changes

### Pull Request Checklist

- [ ] Code follows project style guidelines
- [ ] Tests pass locally
- [ ] Documentation is updated
- [ ] Commit messages follow conventional commits format
- [ ] PR description clearly describes the changes
- [ ] No merge conflicts

### Pull Request Template

Use the provided PR template when creating pull requests.

## Reporting Issues

### Bug Reports

Use the bug report issue template and include:
- Clear description of the bug
- Steps to reproduce
- Expected behavior
- Actual behavior
- Environment details (OS, Python version)
- Logs or error messages

### Feature Requests

Use the feature request issue template and include:
- Clear description of the feature
- Use case for the feature
- Possible implementation approach
- Any alternatives considered

## Areas Where Help Is Needed

- Adding more site overrides for difficult-to-scrape sites
- Improving extraction accuracy
- Adding tests
- Documentation improvements
- Performance optimizations

## Questions?

Feel free to open an issue for questions or discussion!
