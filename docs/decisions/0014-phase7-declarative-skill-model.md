# ADR 0014: Phase 7 Declarative Skill Model

## Status

Accepted for Phase 7.

## Context

Phase 7 adds owner-authored reusable skills. Skill manifests, imported files,
templates, test fixtures, MCP metadata, retrieved documents, and model output are
untrusted data. A skill must combine instructions, JSON Schemas, retrieval
settings, model policy, approval policy, and explicit tools without arbitrary code
execution.

Phase 4 already provides a bounded agent runtime, tool allowlists, approval
records, and persisted events. Phase 6 adds MCP tools behind server-side
deny-by-default policy. Skills should map into those boundaries rather than
creating another execution path.

## Decision

Use a strict declarative manifest:

```yaml
apiVersion: loomi.dev/v1
kind: Skill
metadata:
  name: research-summary
  version: 1.0.0
  description: Produce a cited summary from selected knowledge sources
spec:
  inputSchema: {}
  outputSchema: {}
  promptTemplate: ""
  retrievalPolicy:
    mode: hybrid
    topK: 8
  allowedTools:
    - knowledge.search
  approvalPolicy: {}
  modelPolicy:
    capability: reasoning
    maxInputTokens: 12000
    maxOutputTokens: 2000
  limits:
    maxSteps: 6
    maxToolCalls: 3
    timeoutSeconds: 120
```

The canonical persisted form is JSON with sorted keys, compact separators, and
ASCII escaping. The checksum is SHA-256 over that canonical JSON.

The database model keeps a skill container and immutable skill versions:

- `skills`: owner, normalized name, display name, lifecycle state, current version,
  provenance, and timestamps.
- `skill_versions`: manifest, checksum, version, lifecycle state, parent version,
  validation results, publication metadata, provenance, and timestamps.
- `skill_tests`: version-scoped deterministic fixtures.
- `skill_test_runs`: version-scoped deterministic run results.
- `audit_events`: skill creation, validation, publish, archive, disable, import,
  export, dry run, test, and execution events.

Lifecycle states are `draft`, `published`, `archived`, and `disabled`. Published
versions are immutable. Editing a published version creates a new draft version
with `parent_version_id` set to the source version. Archived or disabled versions
cannot execute.

Semantic version validation is strict. Duplicate versions for the same normalized
skill name are rejected. Loomi does not infer breaking changes automatically in
Phase 7 because schema/template semantic compatibility is easy to misclassify.
The API returns deterministic validation facts that can support a future explicit
version-advice feature.

## API Shape

All routes are owner-only under `/api/v1/skills`.

- `GET /api/v1/skills?limit&offset&state` lists paginated skill summaries.
- `POST /api/v1/skills` creates a draft from a manifest.
- `POST /api/v1/skills/validate` validates a manifest without persisting it.
- `GET /api/v1/skills/{skill_id}` gets skill detail and versions.
- `PATCH /api/v1/skills/{skill_id}/versions/{version_id}` updates a draft only.
- `POST /api/v1/skills/{skill_id}/versions/{version_id}/publish` publishes an
  immutable version.
- `POST /api/v1/skills/{skill_id}/versions/{version_id}/archive` archives a
  version.
- `POST /api/v1/skills/{skill_id}/versions/{version_id}/disable` disables a
  version.
- `POST /api/v1/skills/{skill_id}/versions/{version_id}/clone` creates a new
  draft version.
- `POST /api/v1/skills/{skill_id}/versions/{version_id}/dry-run` validates and
  previews the rendered prompt, effective policy, allowed tools, retrieval
  policy, and limits without calling external tools or models.
- `POST /api/v1/skills/{skill_id}/versions/{version_id}/execute` maps the exact
  published version to a Phase 4 agent run.
- `GET /api/v1/skills/{skill_id}/versions/{version_id}/export` exports a
  secret-free manifest package.
- `POST /api/v1/skills/import` validates an import package, shows diff and
  requested permissions, and persists as draft only when requested.
- `GET /api/v1/skills/{skill_id}/versions/{from_id}/diff/{to_id}` returns a
  structured version diff.
- `GET/POST/PUT/DELETE /api/v1/skills/{skill_id}/versions/{version_id}/tests`
  manages deterministic tests.
- `POST /api/v1/skills/{skill_id}/versions/{version_id}/tests:run` stores a
  deterministic test run.

Mutating routes require CSRF. Create, clone, execute, import, export, and test
run routes use idempotency keys where duplicate side effects matter.

## Execution Mapping

At execution time Loomi:

1. loads the immutable published version by owner and version ID;
2. validates owner input against the manifest input schema;
3. resolves model capability through server policy;
4. computes `allowedTools` as the intersection of the skill allowlist and the
   runtime/server allowlist;
5. applies the stricter value between global and skill limits;
6. renders the prompt through the Phase 7 safe renderer;
7. creates a persisted Phase 4 `AgentRun` with `run_kind=skill`;
8. enforces existing runtime approval policy;
9. validates deterministic model/test output against the output schema where
   applicable;
10. records skill ID, version ID, SemVer, checksum, and audit metadata.

## Rejected Alternatives

- Executable Python, JavaScript, shell, SQL, or package-based skill plugins:
  rejected because Phase 7 requires reusable skills without arbitrary code
  execution.
- Editing a published row in place: rejected because execution must use the exact
  published version that was reviewed.
- A separate skill runner bypassing Phase 4: rejected because approvals, tool
  policy, trace events, budgets, and cancellation already live in the agent
  runtime.
- Auto-publishing imported manifests: rejected because import files are
  untrusted and may request broader tool permissions.

## Implementation Inventory

Expected files:

- `apps/api/src/loomi_api/skills/*`
- `apps/api/src/loomi_api/api/skills.py`
- `apps/api/src/loomi_api/db/models.py`
- `apps/api/migrations/versions/20260802_0007_phase7_skills.py`
- `apps/api/tests/test_skills.py`
- `packages/contracts/src/index.ts`
- `apps/web/app/skills/*`
- `docs/skills.md`
- `docs/architecture.md`
- `docs/threat-model.md`
- `README.md`

Expected dependency change: none for Phase 7. JSON import is mandatory. YAML
import remains deferred unless a safe parser is added and locked.

Primary risks:

- treating imported manifest text as instructions;
- accidentally exposing provider secrets in exports or the editor;
- allowing template traversal or expansion abuse;
- weakening server-side MCP/tool/approval policy through skill configuration;
- stale executions if mutable versions are used by ID.
