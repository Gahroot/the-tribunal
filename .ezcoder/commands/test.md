---
name: test
description: Run tests, then spawn parallel agents to fix failures
---

Run all tests for the frontend and backend, collect failures, and use the `subagent` tool to spawn parallel sub-agents to fix them.

Monorepo: `frontend/` uses **Vitest**, `backend/` uses **pytest**.

## Step 1: Run Tests

```bash
# Frontend unit/component tests
cd frontend && npx vitest run

# Backend tests
cd backend && uv run pytest tests/ -v --tb=short
```

Options:
- **Watch mode** (during active development): `cd frontend && npx vitest` or `cd backend && uv run pytest tests/ -f`
- **Coverage**: `cd frontend && npx vitest run --coverage` or `cd backend && uv run pytest tests/ --cov=app --cov-report=term-missing`
- **Filter**: `cd frontend && npx vitest run path/to/test` or `cd backend && uv run pytest tests/path/to/test.py -k "test_name"`
- **Just unit**: `cd backend && uv run pytest tests/utils/ tests/services/ tests/schemas/ -v`
- **Just API integration**: `cd backend && uv run pytest tests/api/ -v`

## Step 2: Collect Failures

Parse the output from both test runs. Group failures by:
- **Frontend failures**: React component rendering, hook behavior, utility function errors
- **Backend unit failures**: Utility, service, schema, or worker logic errors
- **Backend integration failures**: API endpoint, validation, or auth errors

## Step 3: Spawn Parallel Agents

For each group with failures, use the `subagent` tool (agent: `bee`) to spawn a sub-agent. Invoke all sub-agents in **a single tool-call block** so they run in parallel.

Each sub-agent prompt must be fully self-contained (sub-agents have no context). Include:
1. The exact command to re-run to see the errors.
2. The full list of failing tests and their error messages.
3. The source file paths involved.
4. Rules: fix the underlying code (not the test), follow project conventions, re-run to confirm zero failures.

## Step 4: Re-run All Tests

After all agents complete, re-run the full test suite:

```bash
cd frontend && npx vitest run
cd backend && uv run pytest tests/ -v --tb=short
```

Report the final status. If any failures remain, fix them directly or spawn another round.
