---
name: commit
description: Run checks, commit with AI message, and push
---

1. Run quality checks — fix ALL errors before continuing:
   ```
   cd frontend && npm run lint && npm run build
   cd backend && uv run ruff check app tests --fix && uv run mypy app
   ```

2. Run `git status`, `git diff --staged`, and `git diff` to review changes.

3. Stage relevant files with `git add` (specific files, not `-A`).

4. Generate a commit message: start with a verb (Add/Update/Fix/Remove/Refactor), be specific and concise, one line.

5. Commit and push:
   ```
   git commit -m "your generated message"
   git push
   ```
