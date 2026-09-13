# Django

Follow Django community best practices; `rules/python.md` applies throughout.

## Structure & ownership

- Behavior lives on the type that owns the data: query logic → querysets/managers, entity behavior → model methods, serialization → the serializer that declares the fields. Prefer `obj.action(...)` over `Helper.action(obj)` or a classmethod whose first arg *is* that object.
- Coordinators stay thin: logic spanning several entities is a small function in its own module, not bolted onto one entity. Coordinators (tasks, signal receivers, views, serializer `create()`/`update()`) only schedule and delegate — the real logic sits on querysets/models; task queueing lives next to the write that causes it, in whichever coordinator owns that write.
- Right-size abstractions *(judgment — propose, don't assume)*: a stateless one-method class is just a function; add a class only for state, a reuse boundary, or an injectable/mockable seam. Don't collapse an abstraction that has real, anticipated reuse.
- Functions passing around the same field bundle are a missing object — collect them into a (frozen) dataclass, behavior as methods; likewise module constants + helpers orbiting one concept are a class (fields = tuning knobs with production defaults).
- Framework behavior is fixed in settings, never per call site — timezone, DRF date formats and the like are configured once, not via per-field overrides, `timezone.override`, or template tz tags.

## Models and QuerySets

- `objects` managers must be defined after fields.
- Retrieval-only queryset methods take generic community names (`get_or_none(**kwargs)`); a family of same-shaped filters collapses into one parametrized method with the enum visible at call sites (`event_type(EventType.signup)`); sibling state filters share one zero-arg contract with cutoffs derived inside.
- Constructor classmethods are named by lifecycle: `load()` = once/expensive (parked in a constant), `current()` = cheap/per-call/fresh, `of_user(x)` = scoped by its argument; a zero-arg signature says "global". Plain `__init__` stays the test door.
- A field with a static default declares both `default` and `db_default`: `default` gives unsaved instances the real value (no `DatabaseDefault` sentinel), `db_default` keeps the column's DEFAULT in the database so inserts from not-yet-swapped code stay valid during a deploy window. Dynamic (callable) defaults stay Python-only.
- Async manager/queryset methods wrap their sync counterparts via `sync_to_async`, like Django's own `acreate`.

## DRF

- Prefer declarative serializer `source=` fields over `SerializerMethodField`; reserve method fields for genuine computation (conditionals, indexing, transforms). Keep `source=` chains (`source="get_thing.value"`) shallow — a deep chain can hide N+1s, so make sure the queryset prefetches what it touches.
- Enforce important invariants at the DB level (constraints) on top of app-level checks, and handle the race safely (savepoint + catch `IntegrityError`) so it doesn't abort the surrounding transaction. Lean on Django's built-in field validation; don't add `clean()`/custom validators for guards you don't actually need.
- Don't over-defend data the caller/trigger guarantees *(judgment — only when the guarantee is real)*: skip `None`-guards where the operation that runs the code ensures the data exists; let a genuine gap raise rather than silently emit a partial result.
- DRF exceptions and action preconditions live in the API app (`<feature>/validators.py` raising DRF `ValidationError`) — the package path answers "is this framework import OK here"; never raise DRF exceptions from a domain app.
- Write serializers are named `...InputSerializer`.
- Keep viewsets thin — config + `get_queryset` + thin actions, no lookup/validation boilerplate:
  - Inherit `list`/`retrieve`/etc. from DRF mixins instead of hand-writing them.
  - Push every lookup onto a queryset method the view delegates to in one line — `get_object` → `Model.objects.get_or_stub(...)`; writes → an upsert method (`set_state`).
  - An action that validates one serializer and responds with another pushes both into the input serializer — `create()`/`update()` own the write, `to_representation` delegates to the read serializer — so the action shrinks to bind → validate → save → respond, or just `return self.create(request)`.
  - Validate a URL path key once at the routing boundary, sourced from the model enum (`re_path` over `Kind.values`), so an unknown key 404s before the view and nothing downstream re-checks it (an instance of the don't-over-defend rule).
  - A read-only serializer needs no explicit `read_only_fields` when its viewset only serves reads.

## Translations (i18n)

- **Do not** regenerate catalogs or translate until asked — translation happens at the very end of an implementation, after the wording is confirmed final.
- Translating is the `i18n-translate` skill's job — use it when asked.
