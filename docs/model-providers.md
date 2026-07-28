# Model Providers

Phase 3 introduces a provider-neutral gateway under the API service.

## Providers

- `mock`: deterministic local provider for CI and demos.
- `openai-compatible`: generic Chat Completions wire-format endpoint.
- `openai`: OpenAI Chat Completions endpoint through the same adapter shape.
- `anthropic`: Anthropic Messages API adapter.
- `gemini`: Gemini `generateContent` adapter.
- `vllm`: local vLLM through an OpenAI-compatible endpoint.

Provider SDK objects are not exposed to retrieval, chat orchestration, FastAPI response models, or the browser. Provider errors are normalized and secrets are never returned in responses.

## Configuration

Use environment variables:

```text
LOOMI_CHAT_PROVIDER=mock
LOOMI_CHAT_MODEL=loomi-mock-cited-chat-v1
LOOMI_OPENAI_COMPATIBLE_BASE_URL=
LOOMI_OPENAI_COMPATIBLE_API_KEY=
LOOMI_OPENAI_API_KEY=
LOOMI_ANTHROPIC_API_KEY=
LOOMI_GEMINI_API_KEY=
LOOMI_VLLM_BASE_URL=
LOOMI_MODEL_REQUEST_TIMEOUT_SECONDS=30
LOOMI_MODEL_MAX_RETRIES=2
LOOMI_MODEL_MAX_OUTPUT_TOKENS=800
LOOMI_MODEL_MAX_ESTIMATED_COST_USD=0.25
```

Fallback providers are disabled by default. Choose one provider per request or through `LOOMI_CHAT_PROVIDER`.

## Security Notes

Provider keys are server-side only. They must not be placed in `NEXT_PUBLIC_*`, browser storage, logs, trace payloads, user feedback, or model-visible retrieved context.
