# ADR 0003: Provider-Neutral Model Gateway

## Status

Accepted.

## Context

Loomi-Brain must support OpenAI-compatible APIs, OpenAI, Anthropic, Google Gemini, local vLLM, and optional future providers. Provider secrets must remain server-side, and the application must support separate models for chat, classification, embeddings, optional reranking, and optional vision/OCR.

## Decision

Create internal provider protocols and use LiteLLM only behind an adapter. Do not expose LiteLLM types or provider-specific SDK details to the API, agent runtime, retrieval system, or frontend.

## Consequences

- Vendor changes stay localized.
- Mock providers can implement the same contracts.
- Provider health checks, token accounting, timeouts, retry policy, rate limits, and cost estimation can be enforced consistently.
- LiteLLM version churn is isolated from domain code.
