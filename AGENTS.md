# Repository Guidance

## Git workflow

- Treat this directory as a Git repository and inspect `git status --short` before making changes.
- Preserve existing uncommitted work. Never reset, discard, overwrite, or revert changes that were not made for the current task.
- Keep changes focused on the requested work and review `git diff` and `git diff --check` before considering the task complete.
- Run the relevant tests and formatting checks documented in `docs/testing.md` before committing.
- Commit and push only when the user explicitly requests it. Use focused commit messages that explain the completed change.
- Do not amend commits, rebase shared work, force-push, or otherwise rewrite history unless the user explicitly requests that operation.
- Use `main` as the default branch and keep the configured `origin` remote pointed at the canonical GitHub repository.

## Project conventions

- Keep production modules in their numbered reading order and retain namespace-qualified module calls.
- Preserve Python 3.8.3 compatibility and the configured 160-column formatting limit.
- Keep generated caches, package metadata, build output, credentials, and local environments out of version control.
