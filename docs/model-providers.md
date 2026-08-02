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

## Speech Providers

Phase 9 adds speech providers under `loomi_api.voice`, separate from the chat LLM
gateway:

- `mock`: deterministic local STT and mock WAV TTS for CI/demo.
- `browser`: browser speech synthesis for local TTS playback; no server provider call.
- `openai`: server-side OpenAI audio transcription and speech endpoints.
- `local-compatible`: OpenAI-compatible local speech endpoint, such as a
  faster-whisper service exposing `/v1/audio/transcriptions`.

Voice transcripts are owner input and are submitted through the existing cited-chat
pipeline only after review by default. Speech-provider metadata is never treated as
instructions.

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
LOOMI_VOICE_STT_PROVIDER=mock
LOOMI_VOICE_STT_MODEL=loomi-mock-transcribe-v1
LOOMI_VOICE_TTS_PROVIDER=browser
LOOMI_VOICE_TTS_MODEL=loomi-browser-speech-synthesis
LOOMI_VOICE_CLOUD_ENABLED=false
LOOMI_VOICE_OPENAI_STT_MODEL=gpt-4o-mini-transcribe
LOOMI_VOICE_OPENAI_TTS_MODEL=gpt-4o-mini-tts
LOOMI_VOICE_LOCAL_STT_BASE_URL=
LOOMI_VOICE_LOCAL_TTS_BASE_URL=
```

Fallback providers are disabled by default. Choose one provider per request or through `LOOMI_CHAT_PROVIDER`.

## Security Notes

Provider keys are server-side only. They must not be placed in `NEXT_PUBLIC_*`, browser storage, logs, trace payloads, user feedback, voice transcripts, TTS text, or model-visible retrieved context. Cloud speech is disabled until explicitly enabled through configuration/settings.
