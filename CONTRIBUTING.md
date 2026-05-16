# Contributing to The Tribunal

Thanks for your interest in contributing! This guide covers local setup, branching, commits, and the checks you need to run before opening a pull request.

## Prerequisites

- **Docker** + Docker Compose (for PostgreSQL 17 and Redis 7)
- **Python 3.12+** and [`uv`](https://docs.astral.sh/uv/) for the backend
- **Node.js 20+** and **npm** for the frontend
- A `.env` file in `backend/` (see `backend/.env.example`) and `frontend/.env.local` (see `frontend/.env.example`)

## Development Setup

### Backend (`backend/`)

```bash
cd backend
docker compose up -d              # PostgreSQL + Redis
uv sync                           # Install Python dependencies
uv run alembic upgrade head       # Apply database migrations
uv run uvicorn app.main:app --reload --port 8000
```

The API will be available at <http://localhost:8000> and the OpenAPI docs at <http://localhost:8000/docs>.

### Frontend (`frontend/`)

```bash
cd frontend
npm ci                            # Clean install of locked dependencies
npm run dev                       # Dev server on :3000
```

The app will be available at <http://localhost:3000>.

## Branch Naming

Create a branch off `main` using one of the following prefixes:

| Prefix      | Use for                                       | Example                              |
| ----------- | --------------------------------------------- | ------------------------------------ |
| `feat/`     | New features or user-visible capabilities     | `feat/sms-campaign-scheduler`        |
| `fix/`      | Bug fixes                                     | `fix/contact-filter-pagination`      |
| `refactor/` | Internal restructuring without behavior change | `refactor/extract-contact-filters`   |
| `chore/`    | Tooling, deps, build, CI, docs-only changes   | `chore/bump-react-query`             |

Keep branch names short, lowercase, and hyphen-separated.

## Commit Style — Conventional Commits

We follow [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/). Format:

```
<type>(<optional scope>): <short description>

<optional body>

<optional footer (e.g. BREAKING CHANGE:, Closes #123)>
```

Allowed types: `feat`, `fix`, `refactor`, `chore`, `docs`, `test`, `perf`, `build`, `ci`, `style`, `revert`.

Examples:

```
feat(campaigns): add weekday-only sending window
fix(contacts): handle null phone in segment filter
refactor(api): extract apply_contact_filters helper
chore(deps): bump fastapi to 0.115
```

- Use the imperative mood ("add", not "added").
- Keep the subject line ≤ 72 characters.
- Append `!` after the type/scope or include `BREAKING CHANGE:` in the footer for breaking changes.

## Pre-Commit Hooks

This repo runs two layers of pre-commit automation. Install both before your first commit.

### 1. `pre-commit` framework (repo-wide)

Runs generic hygiene checks, `ruff check` + `ruff format` on the backend, and `gitleaks` for secret scanning. Configured in [`.pre-commit-config.yaml`](./.pre-commit-config.yaml).

```bash
pipx install pre-commit          # or: brew install pre-commit
pre-commit install               # installs the git hook into frontend/.husky
pre-commit run --all-files       # one-time sweep of the whole repo (optional)
pre-commit autoupdate            # bump hook versions periodically
```

Included hooks:

- `end-of-file-fixer`, `trailing-whitespace`, `check-yaml`, `check-toml`, `check-merge-conflict`
- `check-added-large-files` — rejects anything over **500 KB**
- `ruff` (`--fix`) and `ruff-format` — scoped to `backend/`
- `gitleaks` — secret scanner
- Local hooks that run `npm run lint` and `npm run typecheck` when staged files match `frontend/**/*.{ts,tsx}`

### 2. Husky + lint-staged (frontend)

Layered on top of `pre-commit` to give the frontend fast, file-scoped fix-on-save behavior. Configured under `lint-staged` in [`frontend/package.json`](./frontend/package.json) and the hook script in [`frontend/.husky/pre-commit`](./frontend/.husky/pre-commit).

Install (one-time, from the repo root):

```bash
cd frontend
npm install                      # installs husky + lint-staged + prettier as devDeps
npm run prepare                  # wires git core.hooksPath to frontend/.husky
```

The husky `pre-commit` script (1) invokes the `pre-commit` framework against the whole repo, then (2) runs `lint-staged` from `frontend/`, which executes:

- `eslint --fix` on staged `*.ts` / `*.tsx`
- `prettier --write` on staged `*.json` / `*.md`

If you ever need to skip the hooks for a one-off commit (rare — only for emergency hotfixes), use `git commit --no-verify`.

## Lint, Typecheck, and Test

Run the relevant checks **before pushing**. CI runs the same commands and will fail the PR otherwise.

### Backend

```bash
cd backend
uv run ruff check app             # Lint
uv run ruff format --check app    # Formatting
uv run mypy app                   # Type-check
uv run pytest                     # Test suite
uv run pytest tests/api/test_contacts.py::test_list  # Single test
```

### Frontend

```bash
cd frontend
npm run lint                      # ESLint
npm run typecheck                 # tsc --noEmit (if defined; otherwise npm run build)
npm run build                     # Production build — must pass
npm test                          # Unit tests (if defined for the touched area)
```

Fix **all** errors and warnings before opening a PR. There is zero tolerance for failing lint, type, or build steps on `main`.

## Frontend API Mocking with MSW

Frontend tests mock the backend at the **network boundary** with [Mock Service Worker](https://mswjs.io/) (`msw/node`) rather than stubbing `axios`/`fetch` directly. This lets components, hooks, and providers exercise their real data-fetching code paths against a deterministic API.

### Layout

```
frontend/src/test/
  setup.ts          # Vitest globals + MSW lifecycle (listen / reset / close)
  msw/
    server.ts       # setupServer(...handlers) — the Node interceptor
    handlers.ts     # Default "happy-path" stubs for common endpoints
```

The lifecycle is wired once in `setup.ts`:

- `beforeAll(() => server.listen({ onUnhandledRequest: "error" }))` — unhandled requests fail loudly.
- `afterEach(() => server.resetHandlers())` — per-test `server.use(...)` overrides do not leak.
- `afterAll(() => server.close())` — clean teardown.

### Adding a default handler

Default handlers in `handlers.ts` describe the "empty / happy path" — enough for a component to render without crashing. They should **not** encode test-specific data.

1. Identify the endpoint by looking at the matching API client in `frontend/src/lib/api/<resource>.ts`. Use the exact path, including the `:workspaceId` route param.
2. Add (or reuse) a fixture constant at the top of `handlers.ts`. Type it with the response interface from the API client so drift fails type-check, not runtime.
3. Register the handler via the `both(path)` helper so it matches both the proxied origin (`http://localhost:3000`) and the direct backend (`http://localhost:8000`):

   ```ts
   ...both("/api/v1/workspaces/:workspaceId/calls").map((url) =>
     http.get(url, () => HttpResponse.json(stubCallsList)),
   ),
   ```

4. Export any fixture a test might want to reuse (`export const stubCallsList = ...`).

### Overriding for a specific test

Never mutate `handlers.ts` to express test-specific data. Use `server.use(...)` inside the test — it's scoped and auto-reset:

```ts
import { http, HttpResponse } from "msw";
import { server } from "@/test/msw/server";

it("renders the error state when contacts 500", async () => {
  server.use(
    http.get("http://localhost:3000/api/v1/workspaces/:workspaceId/contacts", () =>
      HttpResponse.json({ detail: "boom" }, { status: 500 }),
    ),
  );
  // ...render and assert
});
```

### Conventions

- **Match by absolute URL.** The axios client uses a relative baseURL in jsdom, so requests resolve against `http://localhost:3000`. Register both origins via the `both()` helper to stay robust if a code path ever bypasses the Next.js proxy.
- **Type your fixtures.** Pull the response type from `src/lib/api/<resource>.ts` (e.g. `ContactsListResponse`). A schema change should break the fixture at compile time.
- **Empty by default.** Lists return `{ items: [], total: 0, ... }`. Tests that need populated data override per-test.
- **No `vi.mock("axios")` for API behavior.** If you find yourself reaching for `vi.mock` on `@/lib/api` or `axios`, prefer an MSW override unless you're specifically testing the axios client itself (see `src/lib/api.test.ts`).

## Backend Test Coverage Ratchet

CI enforces a minimum overall backend coverage via `pytest --cov-fail-under=<floor>` in `.github/workflows/backend-ci.yml`. The floor only ever moves **up** — never down.

### Current floor

**49%** (baseline measured at 44% + 5pts starter buffer).

### Policy

1. **Never lower the floor.** If a PR drops coverage below the current floor, fix the PR — do not relax the threshold.
2. **Raise by +5pts whenever a coverage-improvement task completes.** A "coverage task" is any PR whose primary goal is adding tests to lift overall coverage (typically tagged `test:` or `chore(tests):` in the commit). After the PR lands and CI is green on the new tests, bump the `--cov-fail-under=<n>` value in `backend-ci.yml` by 5 in a follow-up commit (or the same PR if it's already green at the new floor).
3. **Incidental coverage gains do not bump the floor.** Only deliberate coverage work moves the ratchet. This keeps the threshold a forcing function for explicit investment rather than a moving goalpost on every feature PR.
4. **Cap at 90%.** Above 90%, additional gains are usually not worth the test churn; revisit the policy before pushing higher.

### How to run coverage locally

```bash
cd backend
uv run pytest --cov=app --cov-report=term-missing
```

Coverage config lives in `backend/pyproject.toml` under `[tool.coverage.run]` and `[tool.coverage.report]`. Migrations, `__init__.py` files, and `app/main.py` are omitted.

## Database Migrations

If your change modifies a SQLAlchemy model:

```bash
cd backend
uv run alembic revision --autogenerate -m "describe change"
uv run alembic upgrade head
```

Review the generated migration by hand — autogenerate is a starting point, not the answer. Never edit a migration that has already shipped; add a new one instead.

## Pull Requests

- Fill out every section of the PR template.
- Keep PRs focused — one logical change per PR.
- Include screenshots or screen recordings for any user-visible frontend change.
- Link the issue you're closing with `Closes #123`.
- Request review from a code owner (see `.github/CODEOWNERS`).

## Code of Conduct

Be respectful, assume good faith, and keep discussions focused on the work. Harassment of any kind is not tolerated.
