---
title: Package Security
---

# Dependency & Package Installation Security Policy

> Applies to every human and every AI agent (Devin, Cascade, scripts, CI) working in this repository.
> **Never install, upgrade, or add a dependency without completing the vetting checklist below.**
> This policy follows the [OpenSSF Concise Guide for Evaluating Open Source Software](https://best.openssf.org/Concise-Guide-for-Evaluating-Open-Source-Software.html),
> the [OpenSSF Package Manager Best Practices](https://github.com/ossf/package-manager-best-practices),
> and lessons from recent supply-chain campaigns (e.g. the 2025 "Shai-Hulud" npm worm waves).

## Why this exists

`pip install` is a remote code execution primitive, not a harmless
convenience. Malicious `setup.py`/build hooks, typosquatted names, and
compromised maintainer releases are the top open-source attack vectors today.
Every dependency is attack surface — treat adding one as a security decision.

## Pre-Install Vetting Checklist

Before installing any package, answer each item and record the result:

### 1. Necessity — build first
- [ ] Always try building the functionality in-repo first: standard
      library, an existing dependency, or a small amount of code. If the
      in-repo implementation works, do not install.
- [ ] Before adding any package, weigh build-yourself vs. third-party
      (implementation effort, maintenance burden, supply-chain surface,
      features gained) and present the comparison with a recommendation —
      proceed only after the user approves the path.
- [ ] Is the package's weight proportionate? (Avoid a 500-dependency tree for a
      one-line utility.)

### 2. Authenticity — defeat typosquatting
- [ ] The package name is verified **character-by-character** against the
      project's official documentation or repository — never guessed.
- [ ] The PyPI page links back to the same source repository you trust
      (bidirectional link check). Watch for attacker-controlled forks.
- [ ] Beware lookalike tricks: swapped letters, hyphens vs underscores,
      and lookalike names (e.g. `beautifulsoup4` vs `beautifulsoup`,
      `requests` vs `request`). PyPI normalizes `-`/`_`/`.`, so check the
      canonical name carefully.

### 3. Reputation & maintenance
- [ ] Download/dependent counts and repository stars/contributors are consistent
      with a real, adopted project — not a near-zero-usage clone.
- [ ] Meaningful commit activity within the last 12 months.
- [ ] A release within the last 12 months.
- [ ] Prefer projects with more than one maintainer; treat single-maintainer
      packages with extra scrutiny.
- [ ] Project shows security-conscious practices: branch protection, CI tests,
      security policy (`SECURITY.md`), timely fix history.

### 4. Vulnerability status
- [ ] The exact version being installed has **no known unpatched Critical or
      High vulnerabilities** in [OSV](https://osv.dev) /
      [deps.dev](https://deps.dev).
- [ ] The package is not listed in the OSV malicious-packages dataset.

### 5. Freshness / provenance
- [ ] Prefer versions published more than **7–30 days** ago. Freshly published
      versions are the highest-risk moment for worm-style supply-chain attacks;
      if a brand-new version is truly needed, justify it explicitly.
- [ ] Where available, prefer packages with provenance attestations /
      Sigstore signatures / published SLSA provenance.
- [ ] Check the project's OpenSSF Scorecard score on deps.dev; treat a score
      below ~5 as a red flag requiring justification.

### 6. Install-time behavior
- [ ] Check whether the package ships code that runs at install time
      (`setup.py` execution, custom build backends, source distributions that
      compile or fetch at build time). Prefer wheels (`--only-binary :all:`)
      when the package works without building from source.
- [ ] Reject packages whose install behavior fetches and executes remote code.

### 7. Determinism
- [ ] Pin **exact** versions (`==`) in `requirements.txt` /
      `requirements-poller.txt` / `pyproject.toml` — no floating or
      unversioned specifiers.
- [ ] Prefer hash-verified installs (`pip install --require-hashes`) and keep
      the requirements files committed so every install verifies package
      hashes.

## Automatic Reject Conditions

Reject the package outright, and stop, if **any** of these hold:

- The exact version has a known unpatched Critical/High vulnerability.
- The package appears in a malicious-packages database (e.g. OSV malicious set).
- The name or repository cannot be verified as authentic (possible typosquat).
- The "package" exists only as a personal fork masquerading as the original.
- Its install behavior requires remote-code-fetch to work.

## After Installing

- Run `pip-audit` and record the result (install it if absent — it is itself a
  vetted, well-known PyPA-adjacent tool).
- Review the transitive dependency tree pulled in (deps.dev or
  `pipdeptree`) — new dependencies drag their own supply chain.
- Update `requirements.txt` / `requirements-poller.txt` / `pyproject.toml`
  and commit them with the change.
- Re-run the project's tests.

## Agent-Specific Rules

AI agents working in this repo must additionally:

- **Report before installing**: present a short vetting summary — package name,
  exact version, purpose/necessity, Scorecard/deps.dev result, vulnerability
  status, publish age — and obtain approval before any install that is not
  already in `requirements*.txt` / `pyproject.toml`. Routine
  `pip install -r requirements.txt` installs of already-vetted dependencies do
  not need re-vetting.
- **Never bypass protections**: no side installs outside the manifests, no
  `curl | sh` installs, no `--no-deps` to smuggle in unvetted code, and no
  `--index-url` / `--extra-index-url` overrides (dependency confusion) —
  packages come only from PyPI.
- **No new registries/sources** without explicit approval — packages come only
  from the default public PyPI index.

## Handy one-liners

```bash
# Look up a package's health + vulnerabilities (no install needed):
open "https://deps.dev/pypi/<pkg>/<version>"

# Audit the current environment / requirements files:
pipx run pip-audit                         # or: pip install pip-audit && pip-audit
pip-audit -r requirements.txt

# Inspect a wheel without installing it:
pip download --no-deps <pkg>==<version> -d /tmp/pkg-inspect
```
