# MCP Security

Phase 6 adds a secure Model Context Protocol client boundary for Loomi-Brain.
MCP servers, capability metadata, prompts, resources, tool schemas, and tool
results are untrusted data. They never become system instructions and they never
change tool policy automatically.

## Supported Transports

- `stdio`: administrator-defined templates only. The browser can select an
  approved template such as `loomi-test`, but cannot provide an executable path
  or shell command string.
- `streamable_http`: remote MCP endpoint using a single HTTP endpoint. HTTPS is
  required outside local/test environments.

HTTP+SSE compatibility is not implemented for new servers.

## Registry Policy

The owner can register, disable, test, refresh, and delete MCP servers through
`/api/v1/mcp`. Server records store display metadata, transport, safe timeout
limits, output-size limits, health state, capability cache, policy state, and
secret references.

Secrets are represented as references, currently `env:NAME`, and are never
returned to the browser. Stdio subprocesses receive a minimal environment plus
explicitly allowlisted names. Remote endpoints receive bearer credentials only
from the configured secret reference.

## Capability Discovery

Discovery collects tools, resources, and prompts, sanitizes display metadata,
normalizes tool schemas to the subset the agent runtime can validate, and caches
schema hashes. Discovered capabilities are disabled by default.

If a tool schema hash changes on refresh, Loomi disables that tool and resets it
to `credential-sensitive` / `risk-based`. Pending approvals also bind to the
schema hash, so a schema change invalidates stale approval.

## Tool Execution

MCP tools are adapted to the Phase 4 `Tool` protocol as dynamic tool IDs:

```text
mcp::<server_id>::<tool_name>
```

Every invocation goes through the agent runtime:

1. owner session and CSRF checks for the invoke request;
2. enabled server check;
3. exact enabled capability check;
4. local schema validation;
5. risk and approval policy evaluation;
6. timeout and output-size enforcement;
7. constrained transport execution;
8. result sanitization and truncation;
9. audit event and telemetry span persistence;
10. return as `untrusted_mcp_result`.

Read-only tools can run without approval if explicitly enabled with
`approval_policy=never`. External mutation, credential-sensitive, destructive,
and unknown tools require approval by default.

## Stdio Hardening

Stdio servers run without a shell using `asyncio.create_subprocess_exec`. Loomi
passes fixed arguments from the allowlisted template, starts a new process group,
drains bounded stderr, bounds stdout, applies startup/tool timeouts, closes stdin
after use, and terminates the process group on timeout.

Production deployments should add stronger isolation around stdio servers:
non-root containers, seccomp/AppArmor, read-only filesystems, CPU/memory limits,
egress controls, and dedicated service accounts.

## Remote Hardening

Remote endpoints are validated before each request. Loomi blocks credentials in
URLs, non-HTTP(S) schemes, redirects, DNS failures, loopback, private,
link-local, metadata, multicast, reserved, and unspecified addresses unless an
administrator explicitly enables a private-network exception outside production.

Credentials are not forwarded across redirects because redirects are blocked.
Response bodies are size-limited and parsed as JSON-RPC or bounded SSE data.

## Test Server

The built-in `loomi-test` stdio template exposes harmless synthetic tools:

- `echo`
- `add`
- `search_notes`
- `large_output`
- `risky_write`
- `env_probe`
- `forbidden_shell`

The last three are policy probes. They do not execute shell or filesystem
operations.
