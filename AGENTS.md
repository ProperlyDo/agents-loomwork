# Agent Instructions

Shared rules for AI agents across our projects.

## Scope and precedence

- Stack rules live in the `rules/` directory next to this file's real location (resolve the symlink you read this through). The project's root `AGENTS.md` declares which apply, via frontmatter: `stacks: [python, django]`. Unless already loaded into your context, read `rules/git.md` plus `rules/<stack>.md` for every declared stack — a declared pair always applies together:
  - `rules/git.md` — always, before any git operation
  - `rules/python.md` + `rules/django.md` — Django backends
  - `rules/typescript.md` + `rules/angular.md` — Angular frontends
- A project may carry its own root `AGENTS.md` — read it before working there; it and the project's `README.md` override these shared rules where they conflict.
- Each project's `README.md` documents its dev stack and commands — setup, services, migrations, fixtures, tests; look there before guessing a command or detail.

## Working style

- Before implementing new methods, classes, or features:
  1. Search the codebase for existing similar functionality
  2. Extend existing code if it nearly fits the need
  3. Ask if unsure whether something exists or should be extended
- Cross-cutting behavior (limits, ledgers, auditing) extends the app's established mechanism — a missing scope/flag on it, never a parallel sibling mechanism, even if simpler.
- After implementing, verify with a quick cheap check (shell/curl for a backend, hot reload in the browser for a frontend) and hand the user a short "what to check" list instead of probing the running system end-to-end yourself; reserve deep verification for risky or hard-to-predict changes.
- Tests must not make real API calls to AI models or third parties — mock/stub them unless explicitly asked.
- Infra changes come with the mechanical why stated first; a hack is either removed or its intent made explicit — the user picks, never silently adjust to a broken setup.

## Naming (all languages)

- Names specific and non-stuttering — don't give an instance the same name as its module; avoid `pkg/pkg.py`.
- No single-letter variable names (`r`, `m`, `e`) — always full descriptive names.
- Avoid dev-overloaded terms (staging, tools, build, client, …) — prefer the business domain's own word.

## Code comments (all languages)

- Comment only the non-obvious *why* — rationale, gotcha, edge case, domain/unit mapping, magic-value meaning. Never restate the code.
- **One comment, one claim.** Needing "and", ";", or a second sentence to carry another fact means splitting it or cutting the weaker half. Two lines is the ceiling — beyond that, fix the names or the structure instead.
- **Put it where it bites** — beside the line that reads wrong without it, not bundled at the top of a block.
- **Write for the next reader, not for a reviewer.** A comment clarifies what the code cannot show; it never argues the code is right. So no justification ("earns its keep", "on purpose", "makes sense because"), no roads not taken ("X would work too, but…"), no speculation about code that does not exist, and no history ("used to", "replaced the old") — git is the changelog.
- **Don't teach the dependency.** Explain our decision, not how the framework behaves; a library fact earns a clause only where the code reads as a bug without it.
- No file-header comments (tooling directives like `# ruff: noqa` excepted).
- E.g. drop `count += 1  # increment count`; keep `# check-then-create can race; the unique constraint is the real guard`.
- Before finishing, re-read every comment you added and cut the ones that restate code, teach a library, justify, or speculate.
