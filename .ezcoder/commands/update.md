---
name: update
description: Update dependencies, fix deprecations and warnings
---

Monorepo: `frontend/` uses **npm**, `backend/` uses **uv**. Run each step for both unless a package is clearly unaffected.

## Step 1: Check for Updates

```bash
cd frontend && npm outdated
cd backend && uv tree --outdated
```

Read the output and note which packages have newer versions (minor/patch vs major). Treat major bumps cautiously — check release notes before upgrading.

## Step 2: Update Dependencies

```bash
# Frontend: safe minor/patch bumps, then audit
cd frontend && npm update && npm audit
cd frontend && npm audit fix        # only if audit reports issues

# Backend: resolve latest compatible versions
cd backend && uv lock --upgrade && uv sync
```

For major version bumps, update `package.json` / `pyproject.toml` manually one package at a time, then re-run install.

## Step 3: Check for Deprecations & Warnings

Do a clean install and read ALL output carefully:

```bash
cd frontend && rm -rf node_modules && npm ci
cd backend && uv sync --reinstall
```

Scan stdout/stderr for:
- `npm warn deprecated ...` lines
- Peer dependency warnings
- Security advisories from `npm audit`
- uv resolver warnings or yanked-version notices
- Breaking-change notes in upgraded package CHANGELOGs

## Step 4: Fix Issues

For each warning/deprecation:
1. Research the recommended replacement (use `web_fetch` on the package's npm/PyPI page or CHANGELOG).
2. Update the dependency or the calling code accordingly (rename imports, swap APIs, adjust config).
3. Re-run the install command for that package.
4. Verify the warning is gone.

## Step 5: Run Quality Checks

```bash
cd frontend && npm run lint && npm run build
cd backend && uv run ruff check app && uv run mypy app
cd backend && uv run pytest
```

Fix ALL errors and new type/lint failures surfaced by the upgrades before completing.

## Step 6: Verify Clean Install

Final sanity pass — fresh install from scratch, zero warnings/errors:

```bash
cd frontend && rm -rf node_modules .next && npm ci && npm run build
cd backend && rm -rf .venv && uv sync && uv run pytest
```

If anything warns or fails, loop back to Step 4.
