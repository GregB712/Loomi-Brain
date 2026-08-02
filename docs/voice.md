# Voice Mode

Voice Mode lets the authenticated owner speak into the browser microphone, review a
transcript, send it through the existing cited-chat pipeline, and optionally hear the
visible assistant answer.

## Overview

The browser records audio only after an explicit owner action. The web app sends the
recording to `/api/v1/voice/transcribe` with the session cookie and CSRF token. The API
validates owner access, MIME type, size, duration metadata, rate limits, and provider
configuration before calling a speech-to-text provider. The transcript is stored as
voice metadata, not as a privileged instruction. The owner can edit it before sending,
and sending uses the existing `/api/v1/conversations/{id}/responses/stream` cited-chat
path.

Text-to-speech reads only visible assistant answer text. Browser speech synthesis is
the default local playback path. Server-side TTS is available through mock, OpenAI, or
OpenAI-compatible local providers.

## Local Demo Mode

Defaults from `.env.example`:

```text
LOOMI_VOICE_STT_PROVIDER=mock
LOOMI_VOICE_TTS_PROVIDER=browser
LOOMI_VOICE_DEMO_MODE=true
LOOMI_VOICE_RETAIN_RAW_AUDIO=false
LOOMI_VOICE_CLOUD_ENABLED=false
```

Mock STT returns `LOOMI_VOICE_MOCK_TRANSCRIPT` deterministically for demos and CI.
Browser TTS uses `window.speechSynthesis` when the browser supports it. No provider key
is required.

## Cloud Provider Setup

Cloud speech is disabled until the owner enables it in Voice settings and the server has
provider credentials. For OpenAI:

```text
LOOMI_OPENAI_API_KEY=<secret-reference>
LOOMI_VOICE_CLOUD_ENABLED=false
LOOMI_VOICE_OPENAI_STT_MODEL=gpt-4o-mini-transcribe
LOOMI_VOICE_OPENAI_TTS_MODEL=gpt-4o-mini-tts
```

Set `LOOMI_VOICE_CLOUD_ENABLED=true` only after reviewing data-processing and cost
implications. The browser never receives the API key. The API calls OpenAI-compatible
audio endpoints server-side and normalizes provider errors before returning them.

## Local Speech Setup

Use `local-compatible` for a local service that implements OpenAI-compatible audio
routes:

```text
LOOMI_VOICE_STT_PROVIDER=local-compatible
LOOMI_VOICE_STT_MODEL=whisper-1
LOOMI_VOICE_LOCAL_STT_BASE_URL=http://local-speech:8000/v1
LOOMI_VOICE_TTS_PROVIDER=local-compatible
LOOMI_VOICE_TTS_MODEL=tts-1
LOOMI_VOICE_LOCAL_TTS_BASE_URL=http://local-speech:8000/v1
```

`faster-whisper`-based services can work on CPU for short recordings, but CPU latency can
be high. GPU improves throughput but is not required for Loomi-Brain's mock/demo path.
Do not expose local speech, vLLM, or MCP services directly to the public internet.

## Privacy Model

- Microphone access starts only after clicking or pressing the voice control.
- There is no always-on listening and no wake-word detection.
- Raw audio is not stored by default.
- Transcripts are persisted because they become owner-visible conversation metadata.
- Provider keys remain server-side.
- Telemetry captures provider/model, duration, size, latency, status, trace ID, and safe
  error codes, not raw audio or unrestricted transcript content.

## Audio Retention

Raw audio retention is off by default. If the owner enables retention, the API stores
audio under private object storage with an explicit retention window and exposes
`DELETE /api/v1/voice/sessions/{id}/audio` to remove retained audio.

## Provider Configuration

Owner-visible settings include STT provider/model, TTS provider/model/voice, language,
max recording duration, max audio size, transcript review, auto-speak, raw audio
retention, retention days, demo mode, and cloud enablement.

Accepted upload MIME types are `audio/webm`, `audio/wav`, `audio/x-wav`, `audio/mpeg`,
`audio/mp3`, `audio/mp4`, `audio/ogg`, `audio/flac`, and `audio/aac`.

## Browser Compatibility

Recording requires `navigator.mediaDevices.getUserMedia` and `MediaRecorder`. Playback
uses `speechSynthesis` for browser TTS or an audio data URL for server TTS. Browsers may
use different recording containers; Loomi-Brain prefers WebM/Opus when available.

## Security Limitations

Speech transcripts can contain errors or background speech. Transcript review is enabled
by default, and voice cannot approve tools, MCP calls, skill execution, destructive
actions, or credential-sensitive operations. Those still require visual UI confirmation
through the existing approval flow.

## Troubleshooting

- If recording is blocked, check the browser permission prompt and the page
  `Permissions-Policy`.
- If OpenAI returns `provider_not_configured`, verify `LOOMI_OPENAI_API_KEY`.
- If OpenAI returns `cloud_speech_disabled`, enable cloud speech intentionally in
  settings or environment.
- If local-compatible providers fail, verify the `/v1/audio/transcriptions` and
  `/v1/audio/speech` routes, timeouts, and payload limits.
- If audio is too large, reduce `LOOMI_VOICE_MAX_RECORDING_SECONDS` or browser recording
  bitrate, or increase `LOOMI_VOICE_MAX_AUDIO_BYTES` after reviewing DoS risk.

## Test Commands

```bash
cd apps/api && uv run pytest tests/test_voice.py
make lint
make typecheck
make test
make security
corepack pnpm build
```
