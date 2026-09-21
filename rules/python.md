# Python

## Dependencies

- Package manager: `uv`.
- Direct dependencies stay pinned exact (`==`) in `pyproject.toml`; transitives are refreshed via the lockfile only — `uv lock --upgrade` (or `--upgrade-package X` for a surgical bump)
- Each dependency carries a very short trailing comment naming its purpose (`"django-storages[s3]==1.14.6",  # media on S3`)

## Rules

- Imports live at module top; an in-body import is allowed only to break a real circular dependency, with the cycle named in a comment next to it. Don't imitate existing in-body imports — most are historical, not cycle breaks.
- Respect layering / import direction: a lower-level module must not import a higher-level one at runtime — use `TYPE_CHECKING` for type-only references and lazy (function-local) imports otherwise. Code that must reach "up" belongs in the coordinating layer, not on the low-level type.
- When overriding a method, extend — don't replace: adjust the inputs the parent works from (or its result) and always `return super().method(...)`; reimplementing the parent's logic in a branch is a last resort.
- Prefer class-scoped constants over module-level ones — define a value on the class it belongs to (e.g. `Model.TIMEOUT_SECONDS`); keep it at module scope only when it isn't tied to one class.
- Reference canonical definitions; don't restate their values — a slug/choice/constant defined once (an enum, `Choices`, settings) is imported and referenced (`Model.SLUGS.x`), never re-typed as a literal; duplicated literals drift silently on rename.
- Right-size constants — inline a value used once when the expression already reads clearly (enum members, a lone literal); name a constant only for reuse, or when the name says something the literal doesn't.
- Never shadow builtin or stdlib names (`property`, `type`, `id`, `file`, `list`, `filter`, …) with variables, parameters, or comprehension targets.
- Don't use `_` as a throwaway in unpacking — index the element you need (`x = pair[1]`). In modules that import `gettext_lazy as _`, a throwaway `_` shadows it.
- Underscore-prefix only what nothing outside the module reaches — tests count as outside: a helper that tests patch is the module's seam and gets a public name.
- Inline one-line single-caller helpers — a private helper called from one place, whose body fits on a line, belongs at its call site.
- Order class members newspaper-style: public API first, then the operations it orchestrates, then queries and primitives, trivial derivations last.

## Typing

- Annotate new and touched code.
- Bare names in annotations, never quoted strings.
- No `from __future__ import annotations` on Python 3.14+ — annotations are lazy there, and the import forces the old string form that runtime readers like pydantic must resolve. Below 3.14 it stays, as the only way forward references work.
- Imports needed only for annotations go under `TYPE_CHECKING`.

## Docstrings

- One line, and only when name + signature don't make behavior clear. A second line only for a caveat the signature cannot carry. Skip params and types — they are in the signature.
- No module docstrings.
