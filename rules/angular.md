# Angular

Follow Angular community best practices; `rules/typescript.md` applies throughout.

- Package manager: `pnpm`.
- Use modern Angular signals
- Don't run `ng build` just to verify a change — the dev server's hot reload covers that; after completing a task, restart containers to apply changes: `docker compose down --remove-orphans && docker compose up -d`

## Tailwind CSS

- Use the project's configured class prefix on every Tailwind class (e.g. `tw:flex tw:gap-4`, never bare `flex gap-4`)
- Use Tailwind only when it simplifies implementation; avoid if it makes code harder to read
  - Good fit: single-purpose utility rules (flex wrappers, spacing, centering, widths) — prefer utility classes over one-off SCSS rules
  - Bad fit: designed blocks (typography scales, cards, animations, anything with media queries or many properties) — keep those in SCSS; a class combination used 3+ times is also better as one SCSS rule than repeated utility soup
  - Bad fit: arbitrary values with calc/magic numbers (e.g. `tw:lg:max-h-[calc(100vh_-_96px)]`) — write a component-scoped SCSS rule with a comment explaining the derivation instead
- Reuse the app's existing theme colors (CSS variables); ask if none fit the need
- Follow UI/UX best practices when designing interfaces

## SCSS

- Write idiomatic nested SCSS, not flat CSS: nest child selectors inside their structural parent block (mirroring the DOM) and use `&` for variants/states (`&.featured`, `&:hover`), nested `@media` inside the rule they modify
- Keep full class names when nesting (`.signup-form { .signup-form-title { … } }`), not `&`-suffix concatenation — names must stay greppable
- Keep nesting to ~3 levels; self-contained widgets (e.g. an animated illustration) get their own top-level block instead of deepening a section's tree
- `@keyframes` stay top-level; styles for elements that get re-parented to `<body>` (CDK drag previews, overlays) must not be nested under an ancestor selector
- Component-specific Material overrides go through `mat.*-overrides()` token maps; app-wide ones live in the global Material theming directory (one file per component)
- No feature-scoped classes in global stylesheets — global files hold only tokens, element-level defaults, and Material theming; feature styling lives in the feature's component SCSS

## Translations (i18n)

- All user-facing strings must be marked for translation:
  - HTML: `<span i18n>Text</span>` or `<input placeholder="..." i18n-placeholder />`
  - TypeScript: ``$localize`Text` ``
- **Do not** extract or translate strings until asked — translation happens at the very end of an implementation, after the wording is confirmed final
- Translating is the `i18n-translate` skill's job — use it when asked
