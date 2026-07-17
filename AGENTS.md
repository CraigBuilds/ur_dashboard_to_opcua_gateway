# Repository Guidance

## Git workflow

- Before editing any tracked file, run `git status -sb`, confirm the current branch and upstream, and understand all existing changes in the worktree.
- Start unrelated new work from an up-to-date `main` on a focused branch. Use `git pull --ff-only` when synchronizing so an unexpected divergence stops for an
  explicit decision instead of creating an automatic merge commit.
- Treat this directory as a Git repository and inspect `git status --short` before making changes.
- Preserve existing uncommitted work. Never reset, discard, overwrite, or revert changes that were not made for the current task.
- Keep changes focused on the requested work and review `git diff` and `git diff --check` before considering the task complete.
- Run the relevant tests and formatting checks documented in `docs/testing.md` before committing.
- Before committing, stage only the intended files and review `git diff --cached`, `git diff --cached --check`, and `git status -sb`.
- Commit and push only when the user explicitly requests it. Use focused commit messages that explain the completed change.
- Do not amend commits, rebase shared work, force-push, or otherwise rewrite history unless the user explicitly requests that operation.
- Use `main` as the default branch and keep the configured `origin` remote pointed at the canonical GitHub repository.
- After a pull request is merged, return to `main`, fetch with pruning, and synchronize with `git pull --ff-only` before beginning more work.

## Project conventions

- Keep the gateway application compact, retain its numbered reading order, and use namespace-qualified module calls.
- Preserve Python 3.8.3 compatibility and the configured 160-column formatting limit.
- Treat each project beneath `packages/` as an independently installable distribution: keep its gateway dependencies at zero, put reusable behavior and tests
  inside that project, and install the package projects before the gateway during local, CI, and container verification.
- Keep generated caches, package metadata, build output, credentials, and local environments out of version control.
