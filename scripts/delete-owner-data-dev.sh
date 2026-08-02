#!/usr/bin/env bash
set -euo pipefail

ENVIRONMENT="${LOOMI_ENVIRONMENT:-local}"
if [[ "${ENVIRONMENT}" != "local" && "${ENVIRONMENT}" != "test" ]]; then
  printf 'Refusing deletion outside local/test. LOOMI_ENVIRONMENT=%s\n' "${ENVIRONMENT}" >&2
  exit 2
fi

if [[ "${CONFIRM_DELETE:-}" != "DELETE_LOCAL_OWNER_DATA" ]]; then
  printf 'Refusing deletion. Set CONFIRM_DELETE=DELETE_LOCAL_OWNER_DATA for local/test only.\n' >&2
  exit 2
fi

COMPOSE_FILE="${COMPOSE_FILE:-infra/docker/compose.yml}"
POSTGRES_DB="${LOOMI_POSTGRES_DB:-loomi_brain}"
POSTGRES_USER="${LOOMI_POSTGRES_USER:-loomi}"
OBJECT_VOLUME="${LOOMI_OBJECT_VOLUME:-docker_loomi-api-objects}"

docker compose -f "${COMPOSE_FILE}" exec -T postgres \
  psql \
  --username "${POSTGRES_USER}" \
  --dbname "${POSTGRES_DB}" \
  --set ON_ERROR_STOP=1 <<'SQL'
TRUNCATE TABLE
  audit_events,
  owner_settings,
  auth_accounts,
  sessions,
  provider_configurations,
  documents,
  document_versions,
  ingestion_jobs,
  chunks,
  embeddings,
  tags,
  document_tags,
  collections,
  collection_documents,
  conversations,
  messages,
  message_citations,
  agent_runs,
  agent_events,
  tool_calls,
  approvals,
  skills,
  skill_versions,
  skill_tests,
  skill_test_runs,
  mcp_servers,
  mcp_capabilities,
  user_feedback,
  telemetry_spans,
  evaluation_datasets,
  evaluation_runs,
  evaluation_results,
  users
CASCADE;
SQL

docker run --rm \
  --volume "${OBJECT_VOLUME}:/data" \
  busybox:1.37 \
  sh -c 'find /data -mindepth 1 -maxdepth 1 -exec rm -rf {} +'

printf 'Local/test owner data deleted. Re-run `make seed` or restart the API to reseed the owner.\n'
