# Contracts

This package contains the Phase 2 TypeScript API types and credentialed browser client used by the web app.

The FastAPI OpenAPI document remains the source of truth. `openapi.json` should be regenerated from `loomi_api.main:create_app` whenever backend routes change, and the exported TypeScript types/client must stay aligned with that schema.
