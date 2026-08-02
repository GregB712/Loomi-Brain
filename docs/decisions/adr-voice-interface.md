# ADR: Voice Conversation Interface

## Status

Accepted.

## Context

Phase 9 adds microphone capture, transcription, transcript review, cited-chat
submission, and optional speech playback. Audio, transcripts, provider responses, model
output, retrieved evidence, and tool results are untrusted. Provider keys must remain
server-side, and voice must not bypass owner auth, CSRF, retrieval/citation validation,
agent runtime limits, MCP policy, skills policy, or tool approvals.

## Decision

Implement voice as a separate provider-neutral subsystem:

- `SpeechToTextProvider`
- `TextToSpeechProvider`
- `VoiceSettings`
- `VoiceSessionService`
- explicit audio retention policy

The browser uses `MediaRecorder` only after an explicit owner action. The API exposes
owner-only `/api/v1/voice/*` routes for settings, transcription, TTS, sessions, and audio
deletion. Transcripts are reviewed by default and then submitted through the existing
cited-chat SSE route. Raw audio is not persisted unless the owner enables retention.

The default local mode is deterministic mock STT plus browser TTS. OpenAI and
OpenAI-compatible local endpoints are server-side adapters. Cloud speech remains
disabled unless configured and explicitly enabled.

## Consequences

- Voice input inherits the existing chat, citation, runtime, approval, MCP, skills, and
  observability controls.
- Provider keys never enter the frontend bundle.
- CI and demos do not need paid speech credentials.
- Realtime speech-to-speech and wake-word detection are out of scope for this phase.
- Browser E2E must use mocked microphone APIs unless the test environment supports real
  media devices.

## Alternatives Considered

1. Direct browser-to-provider speech APIs. Rejected because provider keys and data
   processing controls would move to the browser.
2. Raw audio as agent input. Rejected because the runtime is text/citation oriented and a
   multimodal agent design needs separate threat modeling.
3. Realtime voice session as the primary chat transport. Deferred because the current SSE
   cited-chat path already enforces persistence, citations, limits, and cancellation.
