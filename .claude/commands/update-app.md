---
name: update-app
description: Update dependencies, fix deprecations and warnings
---

# Dependency Update & Deprecation Fix

## Step 1: Check for Updates

**Frontend:**
```bash
cd frontend && npm outdated
```

**Backend:**
```bash
cd backend && uv pip list --outdated
```

## Step 2: Update Dependencies

**Frontend:**
```bash
cd frontend && npm update && npm audit fix
```

**Backend:**
```bash
cd backend && uv lock --upgrade && uv sync
```

## Step 3: Check for Deprecations & Warnings

**Frontend:**
```bash
cd frontend && rm -rf node_modules package-lock.json && npm install
```

**Backend:**
```bash
cd backend && uv sync --reinstall
```

Read ALL output carefully. Look for:
- Deprecation warnings
- Security vulnerabilities
- Peer dependency warnings
- Breaking changes

## Step 4: Fix Issues

For each warning/deprecation:
1. Research the recommended replacement or fix
2. Update code/dependencies accordingly
3. Re-run installation
4. Verify no warnings remain

## Step 5: Run Quality Checks

```bash
cd frontend && npm run lint && npm run build
cd backend && uv run ruff check app && uv run mypy app
```

Fix all errors before completing.

## Step 6: Verify Clean Install

Ensure a fresh install works with ZERO warnings:

**Frontend:**
```bash
cd frontend && rm -rf node_modules package-lock.json && npm install
```

**Backend:**
```bash
cd backend && rm -rf .venv && uv venv && uv sync
```
