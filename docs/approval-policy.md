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
- risk class;
- policy version;
- expiration time;
- single-use `used_at` state.

Changing arguments after approval invalidates the approval. The runtime marks the
approval expired, prevents execution, and fails the run safely.

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
