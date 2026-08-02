# Local Deployment Notes

The main local guide is [local-deployment.md](local-deployment.md).

Voice defaults for local/demo use:

- `LOOMI_VOICE_STT_PROVIDER=mock`
- `LOOMI_VOICE_TTS_PROVIDER=browser`
- `LOOMI_VOICE_RETAIN_RAW_AUDIO=false`
- `LOOMI_VOICE_CLOUD_ENABLED=false`

Optional local STT/TTS services should expose OpenAI-compatible audio routes on a
private/local interface and be configured with `LOOMI_VOICE_LOCAL_STT_BASE_URL` and
`LOOMI_VOICE_LOCAL_TTS_BASE_URL`. CPU-only Whisper-compatible services are acceptable for
short recordings but can be slow; GPU is optional, not required for demo mode.
