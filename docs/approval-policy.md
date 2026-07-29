# Approval Policy

Owner approval is a server-side control for risky tools. It is not inferred from model
text and cannot be supplied by retrieved documents or tool output.

## Required Approval

Approval is required for:

- `local-mutation` tools marked approval-required;
- all `external-mutation` tools;
- all `credential-sensitive` tools;
- all `destructive` tools;
- any tool with approval policy `always`.

## Binding

An approval record binds:

- owner ID;
- run ID;
- tool call ID;
- exact tool ID;
- canonical JSON argument hash;
- MCP schema hash for dynamic MCP tools;
- risk class;
- policy version;
- expiration time;
- single-use `used_at` state.

Changing arguments after approval invalidates the approval. For MCP tools, changing
the stored tool schema also invalidates approval because the schema hash is part of
the approval hash payload. The runtime marks the approval expired, prevents execution,
and fails the run safely.

MCP tool IDs use `mcp::<server_id>::<tool_name>` and are resolved from the
owner-scoped MCP registry during validation. Discovered MCP tools are disabled by
default until the owner explicitly enables each tool and assigns its risk policy.

## Decisions

Supported decisions:

- approve;
- deny;
- expire;
- cancel by cancelling the run.

Approved calls resume from `request_tool_approval` into `execute_tool`. Denied, expired,
or argument-changed calls do not execute.

## Audit

The runtime writes audit events for run start, approval requested, approval approved,
approval denied, approval expired, run completion, run failure, and cancellation.
The MCP boundary additionally writes audit events for server registry changes,
connection tests, capability refreshes, policy changes, tool execution, and tool
failures.
