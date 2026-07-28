#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

SECRET_PATTERN='sk-[A-Za-z0-9]{20,}|sk_live_[A-Za-z0-9]+|sk_test_[A-Za-z0-9]+|ghp_[A-Za-z0-9]{36}|gho_[A-Za-z0-9]{36}|glpat-[A-Za-z0-9_-]+|AKIA[A-Z0-9]{16}|xox[baprs]-[A-Za-z0-9-]+|-----BEGIN .*PRIVATE KEY|eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.'

echo "Checking for secret-like patterns..."
if rg --hidden \
  --glob '!/.git/**' \
  --glob '!**/.venv/**' \
  --glob '!**/node_modules/**' \
  --glob '!**/.next/**' \
  --glob '!**/.mypy_cache/**' \
  --glob '!**/.ruff_cache/**' \
  --glob '!**/*.tsbuildinfo' \
  --glob '!scripts/security-check.sh' \
  -n "${SECRET_PATTERN}" "${ROOT_DIR}"; then
  echo "Secret-like pattern detected."
  exit 1
fi

echo "Checking production auth defaults..."
cd "${ROOT_DIR}/apps/api"
set +e
PRODUCTION_CHECK_OUTPUT="$(
  LOOMI_ENVIRONMENT=production PYTHONPATH=src uv run python -c "from loomi_api.config import Settings; Settings()" 2>&1
)"
PRODUCTION_CHECK_STATUS=$?
set -e

if [ "${PRODUCTION_CHECK_STATUS}" -eq 0 ]; then
  echo "Production accepted default local authentication settings."
  exit 1
fi
if ! grep -q "LOOMI_OWNER_PASSWORD must be set in production" <<<"${PRODUCTION_CHECK_OUTPUT}"; then
  echo "${PRODUCTION_CHECK_OUTPUT}"
  echo "Production auth default check failed for an unexpected reason."
  exit 1
fi

echo "Security checks passed."
