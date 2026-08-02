# Private And Hybrid Deployment Notes

The main private/hybrid guide is
[private-hybrid-deployment.md](private-hybrid-deployment.md).

For private speech:

- Run local STT/TTS services on a private host or private network only.
- Configure OpenAI-compatible endpoints with `LOOMI_VOICE_LOCAL_STT_BASE_URL` and
  `LOOMI_VOICE_LOCAL_TTS_BASE_URL`.
- Do not expose local speech, vLLM, or MCP services directly to the public internet.
- If a cloud API talks to private speech, the connector must authenticate, restrict
  routes, enforce audio request/response limits, set timeouts, and fail closed.
