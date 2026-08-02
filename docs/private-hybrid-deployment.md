# Private And Hybrid Deployment

Reader: owner deploying Loomi-Brain without exposing private inference or private documents to the public internet.

Post-read action: choose a private deployment shape and avoid unsafe proxy patterns.

## Option A: Fully Private Machine

Run the full Compose stack on a private machine and reach it over Tailscale, WireGuard, or an equivalent private network.

Recommended defaults:

- Bind public service ports to localhost or private-network interfaces only.
- Keep `LOOMI_MCP_ALLOW_PRIVATE_NETWORKS=false` unless a specific private connector is threat-modelled.
- Use secure cookies and TLS when the browser origin is not plain localhost.
- Keep provider keys in server-side environment variables or secret stores.
- Run backups before updates and rehearse restore against development data.
- Keep vLLM on the private host or private network only.

## Option B: Cloud Web/API With Private Inference

This repository does not ship a generic public-to-private inference proxy. A safe connector must:

- Never expose vLLM directly to the public internet.
- Require TLS and authenticated requests.
- Route over a private network or an outbound connector initiated by the private machine.
- Enforce allowlisted methods and paths.
- Prevent arbitrary proxying.
- Set request, response, and stream limits.
- Set connection and total timeouts.
- Restrict source and destination networks.
- Log redacted request metadata and failure state.
- Fail closed when the private inference endpoint is offline.

If those controls are not implemented, use cloud providers or the local/private full-stack profile instead.

## Failure Behavior

- Private inference offline: model requests fail with a structured provider error; document/search functions remain available.
- Connector timeout: retry only within configured model retry limits.
- Unauthorized connector request: reject and audit.
- Unexpected method/path: reject and audit.
