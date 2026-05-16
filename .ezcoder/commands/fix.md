---
name: fix
description: Run typechecking and linting, then spawn parallel agents to fix all issues
---

Run all linting and typechecking tools across the frontend and backend, collect errors, group them by domain, and use the `subagent` tool to spawn parallel sub-agents to fix them.

This project is a monorepo:
- `frontend/` — Next.js 16 + TypeScript (ESLint + `next build` for type errors)
- `backend/` — FastAPI + Python 3.12 (ruff + mypy --strict)

## Step 1: Run Checks

Run all four checks. Capture stdout+stderr for each so errors can be grouped later. Run in parallel via separate bash calls:

```bash
# Frontend lint (ESLint)
cd frontend && npm run lint

# Frontend typecheck (Next.js build runs tsc)
cd frontend && npx tsc --noEmit

# Backend lint (ruff)
cd backend && uv run ruff check app

# Backend typecheck (mypy strict)
cd backend && uv run mypy app
```

If `npx tsc --noEmit` is too slow or misconfigured, fall back to `cd frontend && npm run build` to surface type errors.

## Step 2: Collect and Group Errors

Parse the output from all four commands. Group errors into four domains:

- **Frontend type errors** — from `tsc` / `next build` (TS#### codes, "Type ... is not assignable", missing props, etc.)
- **Frontend lint errors** — from ESLint (rule IDs like `@typescript-eslint/no-unused-vars`, `react-hooks/exhaustive-deps`)
- **Backend type errors** — from mypy (`error: ... [assignment]`, `[arg-type]`, `[return-value]`, etc.)
- **Backend lint errors** — from ruff (rule codes like `E501`, `F401`, `B008`, `SIM102`, `UP007`)

For each domain, build a concise list: `<file>:<line> — <rule/code> — <message>`.

If a domain has zero issues, skip it — don't spawn an agent for nothing.

## Step 3: Spawn Parallel Agents

For each domain with issues, use the `subagent` tool (agent: `bee`) to spawn a sub-agent. Invoke all sub-agents in **a single tool-call block** so they run in parallel.

Each sub-agent prompt must be fully self-contained (sub-agents have no context). Include:

1. The exact command to re-run to see the errors (e.g. `cd frontend && npm run lint`).
2. The full list of errors you collected for that domain.
3. Strict rules:
   - Fix every listed error. Do not suppress with `// eslint-disable`, `# type: ignore`, `# noqa`, or `any`/`Any` unless there is no alternative — and if so, justify it.
   - Do not refactor unrelated code.
   - Follow the project's existing conventions (see `CLAUDE.md`).
   - After fixing, re-run the command and confirm zero errors remain.
4. The working directory (`frontend/` or `backend/`).

Example sub-agent prompt skeleton:

> You are fixing **backend lint errors** from ruff in `/home/groot/aicrm/backend`.
>
> Re-run with: `cd backend && uv run ruff check app`
>
> Errors to fix:
> - `app/services/foo.py:42 — F401 — 'bar' imported but unused`
> - `app/api/v1/baz.py:88 — SIM102 — Use a single if-statement instead of nested if-statements`
> - ...
>
> Rules: fix every error without `# noqa` suppressions. Do not refactor unrelated code. After fixing, re-run ruff and confirm zero errors. Report what you changed.

## Step 4: Verify

After all sub-agents complete, re-run all four checks yourself:

```bash
cd frontend && npm run lint
cd frontend && npx tsc --noEmit
cd backend && uv run ruff check app
cd backend && uv run mypy app
```

Report the final status per domain. If any errors remain, either fix them directly (if trivial) or spawn another round of sub-agents for the remaining domains.
