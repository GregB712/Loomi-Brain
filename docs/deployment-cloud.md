# Cloud Deployment Notes

The main cloud guide is [cloud-configuration.md](cloud-configuration.md).

Voice cloud mode must remain disabled unless the owner has configured server-side speech
credentials and accepted provider data-processing/cost implications:

```text
LOOMI_OPENAI_API_KEY=<secret-reference>
LOOMI_VOICE_CLOUD_ENABLED=true
LOOMI_VOICE_STT_PROVIDER=openai
LOOMI_VOICE_STT_MODEL=gpt-4o-mini-transcribe
LOOMI_VOICE_TTS_PROVIDER=openai
LOOMI_VOICE_TTS_MODEL=gpt-4o-mini-tts
```

Provider keys must not be exposed through `NEXT_PUBLIC_*`. API, edge, and container
payload limits must allow configured voice uploads while preserving
`LOOMI_VOICE_MAX_AUDIO_BYTES`. Keep raw audio retention off unless an explicit retention
policy is documented.
