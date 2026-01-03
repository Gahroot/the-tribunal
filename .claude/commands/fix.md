---
name: fix
description: Run typechecking and linting, then spawn parallel agents to fix all issues
---

# Project Code Quality Check

This command runs all linting and typechecking tools for this monorepo, collects errors, groups them by domain, and spawns parallel agents to fix them.

## Step 1: Run Linting and Typechecking

Run these commands and collect all errors:

**Frontend:**
```bash
cd frontend && npm run lint 2>&1
cd frontend && npm run build 2>&1
```

**Backend:**
```bash
cd backend && uv run ruff check app 2>&1
cd backend && uv run mypy app 2>&1
```

## Step 2: Collect and Parse Errors

Parse the output from all commands. Group errors by domain:
- **Frontend lint errors**: ESLint issues
- **Frontend type errors**: TypeScript errors from build
- **Backend lint errors**: Ruff issues
- **Backend type errors**: Mypy issues

Create a list of all files with issues and the specific problems in each file.

## Step 3: Spawn Parallel Agents

For each domain that has issues, spawn an agent in parallel using the Task tool.

**IMPORTANT**: Use a SINGLE response with MULTIPLE Task tool calls to run agents in parallel.

Example agents:
- "frontend-lint-fixer" for ESLint errors
- "frontend-type-fixer" for TypeScript errors
- "backend-lint-fixer" for Ruff errors
- "backend-type-fixer" for Mypy errors

Each agent should:
1. Receive the list of files and specific errors in their domain
2. Fix all errors in their domain
3. Run the relevant check command to verify fixes
4. Report completion

## Step 4: Verify All Fixes

After all agents complete, run the full check again:
```bash
cd frontend && npm run lint && npm run build
cd backend && uv run ruff check app && uv run mypy app
```

Ensure all issues are resolved.
