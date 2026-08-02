# ADR 0015: Phase 7 Skill Template And Import Sandbox

## Status

Accepted for Phase 7.

## Context

Skill prompt templates are untrusted. They should let the owner compose reusable
instructions from validated input and deterministic test fixtures, but they must
not expose Python, JavaScript, shell, filesystem, process environment, dynamic
imports, raw SQL, unrestricted HTTP, reflection, or arbitrary object traversal.

Imports are also untrusted. JSON/YAML parsers and template engines can be a
security boundary if chosen casually.

## Template Engine Comparison

### Jinja2 sandbox

Pros:

- Mature syntax, conditionals, loops, filters, and good error messages.
- Familiar to many Python developers.

Cons:

- Not currently a locked dependency.
- The broad expression language creates a large review surface.
- Sandboxing still requires careful object exposure, filter control, and resource
  limits.

Decision: rejected for Phase 7. It is more power than the current skill model
needs.

### Mustache/Chevron-style logic-less templates

Pros:

- Small expression surface.
- Familiar `{{ name }}` syntax.
- Logic-less rendering fits a declarative skill model.

Cons:

- Third-party Python implementations would add a dependency.
- Standard Mustache sections add implicit looping and truthiness rules that need
  bounded collection controls.

Decision: use the syntax shape, but implement a stricter in-repo subset.

### Python `string.Template`

Pros:

- Standard library.
- No expression language.

Cons:

- Identifier grammar does not naturally support structured paths such as
  `input.topic`.
- Error messages and variable discovery are too limited for the editor.

Decision: rejected as the main renderer, but it validates that a no-dependency
approach is practical.

## Decision

Implement a small in-repo renderer with this grammar:

```text
template        = text | placeholder
placeholder     = "{{" path "}}"
path            = identifier ("." identifier)*
identifier      = [A-Za-z_][A-Za-z0-9_]*
```

No loops, conditionals, filters, function calls, arithmetic, imports, includes,
macros, recursive expansion, or attribute access are supported in Phase 7.

Allowed variable roots are:

- `input`: owner-supplied data validated against `spec.inputSchema`;
- `retrieval`: deterministic preview/test retrieval metadata;
- `tools`: deterministic preview/test tool metadata;
- `skill`: non-secret skill metadata.

Only dictionary traversal is allowed. Lists can be rendered only as JSON values
at the exact referenced path; numeric indexing is not part of the grammar. The
renderer rejects callable objects, unknown roots, unknown paths, dunder-like
segments, excessive template size, excessive rendered size, excessive variable
count, and unclosed placeholders. Rendered non-string values use canonical JSON.

Escaping defaults to JSON/plain-text safe output. The renderer is intentionally
not an HTML renderer; UI display must still escape rendered prompts as text.

## Import Format

Phase 7 requires JSON import packages:

```json
{
  "format": "loomi.skill.bundle.v1",
  "manifest": {},
  "tests": []
}
```

YAML remains documented as future work. A future YAML implementation must use a
safe loader, reject custom tags, preserve the same canonical JSON model, and add
malformed/custom-tag tests before enabling the API.

Imports are limited by byte size, parsed as data, validated completely, diffed
against existing owner records, and imported as drafts only. Import never
publishes, never enables tools or MCP servers, and never changes global policy.

Exports contain the canonical manifest, non-sensitive tests when explicitly
requested by the endpoint, checksum, and provenance metadata. Exports never
include provider secrets, secret refs, credentials, private provider
configuration, runtime approvals, or hidden server policy.

## Consequences

- Phase 7 skills are intentionally simple and predictable.
- Deterministic tests can render and validate without a model call.
- Future richer template features need an ADR and explicit bounded-loop tests.
- Owners who need control flow should model it outside the template with explicit
  manifest fields, not executable code.
