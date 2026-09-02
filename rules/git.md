# Git

- **Never** run mutating git commands (commit, push, merge, mv, restore, checkout, reset, rebase, stash, …) unless explicitly asked; read-only (status, log, diff, show, blame) is always fine
- Never commit, push, or branch onto the default branch (`main`/`master`)
- Don't create branches unless asked
- New work branches off the up-to-date default branch — `git switch <default-branch> && git pull`, then `git switch -c <type>/<short-kebab-desc>` (e.g. `feat/invoice-export`)
- Commit: `<type>: <short imperative desc>` — types `feat`/`fix`/`chore` (fold refactor/docs/test/style/ci into `chore`), optional scope, mostly `chore` (e.g. `chore(ci): pin runner image`)
- Subject compact (~50 chars), lowercase, imperative, no trailing period
- Subject lines only — no prose body. A commit covering several concerns lists one
  `<type>: <desc>` line per concern, most significant first:
  ```
  feat: export invoices as csv
  fix: handle empty search results
  chore: bump the linter to 2.0
  ```
- No `Co-Authored-By` or "Generated with …" trailers in commit messages
- Stage only relevant files (check `git status`/`git diff`) — never blind `git add -A`
- One commit per feature is fine; split only for readability
