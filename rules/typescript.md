# TypeScript

- Follow TypeScript best practices for clean, maintainable code
- Private class members carry a leading `_` (`private readonly _cookieName`, `private _load()`); no SCREAMING_CASE — `readonly` already says it is a constant
- Constants used by only one class belong inside it as `private readonly` fields, not module-level `const`s; module scope is only for values shared across exports
- JSDoc: one line, and only when name + signature don't make behavior clear. A second line only for a caveat the signature cannot carry. Skip params and types — they are in the signature.
