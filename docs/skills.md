# Skills

Phase 7 adds safe, declarative, versioned skills. A skill is data: a strict
manifest plus optional deterministic tests. Skill manifests, templates, tests,
imports, retrieval data, MCP metadata, tool results, and model output are
untrusted and never become executable code.

## Manifest

Canonical skill manifests use JSON with `apiVersion: loomi.dev/v1` and
`kind: Skill`.

```json
{
  "apiVersion": "loomi.dev/v1",
  "kind": "Skill",
  "metadata": {
    "name": "research-summary",
    "version": "1.0.0",
    "description": "Produce a cited summary from selected knowledge sources"
  },
  "spec": {
    "inputSchema": {
      "type": "object",
      "properties": {
        "question": { "type": "string", "minLength": 1, "maxLength": 2000 }
      },
      "required": ["question"],
      "additionalProperties": false
    },
    "outputSchema": {
      "type": "object",
      "properties": {
        "answer_text": { "type": "string", "maxLength": 20000 },
        "citations": { "type": "array", "maxItems": 50 }
      },
      "required": ["answer_text"],
      "additionalProperties": true
    },
    "promptTemplate": "Summarize {{ input.question }} using cited evidence.",
    "retrievalPolicy": { "mode": "hybrid", "topK": 8 },
    "allowedTools": ["knowledge.search"],
    "approvalPolicy": { "mode": "runtime" },
    "modelPolicy": {
      "capability": "reasoning",
      "maxInputTokens": 12000,
      "maxOutputTokens": 2000
    },
    "limits": { "maxSteps": 6, "maxToolCalls": 3, "timeoutSeconds": 120 }
  }
}
```

Unknown manifest fields are rejected. Skill names must be normalized lowercase
kebab-case, and versions must use SemVer.

## Templates

Templates support only dictionary-path placeholders:

```text
{{ input.question }}
{{ retrieval.summary }}
{{ tools.results }}
{{ skill.name }}
```

Unsupported syntax is rejected, including loops, filters, calls, imports,
includes, JavaScript, Python, shell, raw SQL, dynamic package installation,
environment/process access, and internal-object traversal. Rendering is bounded
by template size, rendered size, and variable count. Undefined variables fail
strictly.

## Lifecycle

Skill versions move through:

- `draft`
- `published`
- `archived`
- `disabled`

Published versions are immutable. Editing a published skill requires cloning it
to a new draft version. Archived and disabled versions cannot execute.

## Execution

Execution loads the exact published version and maps it into the Phase 4 agent
runtime. The runtime uses:

- owner input validated against `inputSchema`;
- the rendered prompt;
- `allowedTools` intersected with server runtime/MCP policy;
- stricter global and skill limits;
- existing approval policy for risky tools;
- output validation against `outputSchema`;
- skill ID, version, checksum, and version ID in run trace metadata.

Dry run validates input and previews rendered prompt, requested tools, allowed
tools, missing tools, retrieval settings, model policy, effective limits, and
approval requirements. Dry run does not call models or tools.

## Tests

Each version can store deterministic synthetic tests with:

- `fixture.input`
- `fixture.mocked_retrieval_results`
- `fixture.mocked_tool_results`
- `fixture.deterministic_model_result`
- `expected.validation_result`
- `expected.output_schema_result`
- `expected.policy_allowed_tools`
- `expected.citations`

Tests run in isolated deterministic mode and do not call external models or
tools.

## Import And Export

Phase 7 imports JSON bundles:

```json
{
  "format": "loomi.skill.bundle.v1",
  "manifest": {},
  "tests": []
}
```

Imports are size-limited, parsed as data, fully validated, reviewed with a diff
and requested permissions, and persisted as drafts only when the owner chooses
to import. Import never publishes and never enables tools or MCP servers.

Exports include a canonical manifest, checksum, provenance, and tests only when
explicitly requested by query parameter. Exports do not include provider secrets,
secret refs, credentials, private provider configuration, approvals, or hidden
server policy.

## Starter Skills

The API exposes safe starter templates for:

- cited research summary;
- compare selected documents;
- meeting-note action-item extraction;
- study-guide generation;
- CSV dataset profile from already extracted structured data;
- prompt-injection review of a selected document.

Starter skills are ordinary templates and manifests, not privileged code paths.
