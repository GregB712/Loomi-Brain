# Incident Response

Reader: maintainer responding to a suspected security, privacy, or reliability incident.

Post-read action: contain the incident, preserve evidence, recover safely, and document follow-up work.

## Severity

- Critical: credential leak, public exposure of private documents, auth bypass, destructive data loss, or public unsafe tool/MCP execution.
- High: owner session compromise, persistent provider key exposure, backup failure during a live incident, or repeatable denial of service.
- Medium: isolated failed ingestion, telemetry outage, non-sensitive dependency vulnerability, or broken demo flow.
- Low: documentation drift, non-sensitive logging issue, or cosmetic UI failure.

## First 30 Minutes

1. Stop exposed entry points if private data or credentials may be leaking.
2. Preserve logs, audit events, traces, release version, image digests, environment metadata, and recent deployment changes.
3. Revoke provider keys, sessions, MCP credentials, and object-store credentials if exposure is plausible.
4. Disable risky MCP servers and skills.
5. Switch demo traffic to mock providers if live provider behavior is suspect.
6. Create a backup before destructive recovery.

## Evidence To Capture

- Request IDs and trace IDs.
- Owner session IDs and revocation status.
- Audit events for login, session revoke, document deletion, MCP edits, tool approvals, skill publishing, and exports.
- Container image tags and workflow run IDs.
- Dependency scan output and SBOM artifact.
- Backup artifact checksums.

## Recovery

- Restore database and private objects from the same recovery point.
- Re-run migrations only after confirming the target release.
- Re-seed only development credentials in local/test environments.
- Verify owner login, document access, search, chat, agent approvals, MCP policy, skills, and observability.

## Post-Incident

- Write a timeline.
- Identify root cause and missing detection.
- Add a test, check, or runbook step that would have caught it earlier.
- Update residual risks in the release checklist.
- Rotate any credential that may have crossed a trust boundary.
