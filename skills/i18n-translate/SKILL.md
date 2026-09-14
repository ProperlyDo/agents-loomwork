---
name: i18n-translate
description: Translate the pending catalog entries of the current project — Django .po or Angular .xlf. Use when the user asks to translate, fill the catalogs, or finish i18n after an implementation; never run it unprompted.
---

# i18n-translate

Translation is the last step of an implementation — run this only when explicitly asked, after the user confirms the wording is final.

## Steps

1. Extract fresh entries:
   - Django: `docker compose run --rm app python manage.py i18n` (also compiles the catalogs)
   - Angular: `docker compose run --rm app pnpm run i18n`
2. Fill the pending entries:
   - Django (`.po`, under the project's `locale/` directory): fill empty `msgstr`s and resolve `#, fuzzy` entries — fix the translation, drop the fuzzy marker.
     A fuzzy `msgstr` is gettext's guess copied from a similar old entry, so it is often unrelated — translate the `msgid` from scratch and overwrite it, never polish the guess. The `#| msgid` comment names the text it came from; drop it with the marker.
   - Angular (`.xlf`, under `src/locale/`): find `state="new"` entries, replace the English text in `<target>` with the translation, change `state="new"` to `state="translated"`.

## Rules

- Judge a `.po` catalog only with `msgfmt --statistics -o /dev/null <po>` (inside the app container), before and after filling. Never infer pending entries from a line grep: a wrapped translation begins with `msgstr ""` and continues on the following lines.
- Touch only pending entries — never blanket-retranslate the catalog.
- Preserve placeholders exactly: `%(name)s`, `{name}`, and `.xlf` inline elements (`<x .../>`).
- Reuse the catalog's existing terminology for recurring domain terms.
