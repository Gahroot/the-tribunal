---
name: commit
description: Run checks, commit with AI message, and push
---

1. Run quality checks and fix ALL errors before continuing:
   - Frontend: `cd frontend && npm run lint && npm run build`
   - Backend:  `cd backend && uv run ruff check app && uv run mypy app`

2. Review changes: `git status` then `git diff --staged` and `git diff`

3. Stage relevant files: `git add <specific files>` (not `-A`)

4. Generate a commit message:
   - Start with a verb: Add / Update / Fix / Remove / Refactor
   - Be specific and concise, one line preferred

5. Commit and push:
   `git commit -m "your message"`
   `git push`
