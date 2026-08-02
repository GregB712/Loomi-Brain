"use client";

import {
  createLoomiClient,
  type Citation,
  type ConversationDetail,
  type ConversationSummary,
  type ModelCapability,
  type SearchMode,
  type SourceChunk,
  type StreamChatPayload,
  type StreamEvent,
  type VoiceSessionSummary,
  type VoiceSettings,
} from "@loomi/contracts";
import {
  AudioPrivacyNotice,
  MicrophonePermissionNotice,
  SpeechPlaybackControls,
  TranscriptEditor,
  TranscriptPreview,
  VoiceInputButton,
  VoiceModeToggle,
  VoiceProviderBadge,
  VoiceRecorder,
  VoiceSessionTimeline,
  VoiceSettingsPanel,
  StatusPill,
  type SpeechPlaybackState,
  type VoiceCaptureState,
} from "@loomi/ui";
import {
  BrainCircuit,
  Clipboard,
  Home,
  Library,
  Loader2,
  LogIn,
  MessageSquare,
  Mic,
  RotateCcw,
  Search,
  Settings2,
  Send,
  Square,
  ThumbsDown,
  ThumbsUp,
  Volume2,
  Workflow,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { SafeMarkdown } from "./safe-markdown";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export function ChatClient() {
  const apiClient = useMemo(() => createLoomiClient(resolveApiBase()), []);
  const abortRef = useRef<AbortController | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const recordingChunksRef = useRef<Blob[]>([]);
  const recordingStartedAtRef = useRef(0);
  const recordingTimerRef = useRef<number | null>(null);
  const animationFrameRef = useRef<number | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const cancelledRecordingRef = useRef(false);
  const lastRecordingRef = useRef<{ blob: Blob; durationMs: number } | null>(
    null,
  );
  const speechUtteranceRef = useRef<SpeechSynthesisUtterance | null>(null);
  const playbackAudioRef = useRef<HTMLAudioElement | null>(null);
  const [email, setEmail] = useState("owner@loomi.local");
  const [password, setPassword] = useState("");
  const [csrfToken, setCsrfToken] = useState<string | null>(null);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [activeConversation, setActiveConversation] =
    useState<ConversationDetail | null>(null);
  const [models, setModels] = useState<ModelCapability[]>([]);
  const [content, setContent] = useState("What method does hybrid search use?");
  const [mode, setMode] = useState<SearchMode>("hybrid");
  const [provider, setProvider] = useState("mock");
  const [model, setModel] = useState("");
  const [tagFilter, setTagFilter] = useState("");
  const [streamingText, setStreamingText] = useState("");
  const [streamingCitations, setStreamingCitations] = useState<Citation[]>([]);
  const [selectedSource, setSelectedSource] = useState<SourceChunk | null>(
    null,
  );
  const [currentRunId, setCurrentRunId] = useState<string | null>(null);
  const [lastUserMessageId, setLastUserMessageId] = useState<string | null>(
    null,
  );
  const [usage, setUsage] = useState<Record<string, unknown> | null>(null);
  const [trace, setTrace] = useState<Record<string, unknown> | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [voiceEnabled, setVoiceEnabled] = useState(false);
  const [voiceSettings, setVoiceSettings] = useState<VoiceSettings | null>(
    null,
  );
  const [voiceSessions, setVoiceSessions] = useState<VoiceSessionSummary[]>([]);
  const [voiceState, setVoiceState] = useState<VoiceCaptureState>("idle");
  const [captureMode, setCaptureMode] = useState<"click" | "push">("click");
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const [audioLevel, setAudioLevel] = useState(0);
  const [transcriptText, setTranscriptText] = useState("");
  const [editingTranscript, setEditingTranscript] = useState(false);
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const [playbackState, setPlaybackState] =
    useState<SpeechPlaybackState>("idle");

  useEffect(() => {
    return () => {
      cleanupRecording();
      stopSpeechPlayback();
    };
  }, []);

  async function handleLogin() {
    setBusy(true);
    setError(null);
    try {
      const response = await apiClient.login(email, password);
      setCsrfToken(response.csrf_token);
      setPassword("");
      const [conversationList, modelList, loadedVoiceSettings, voiceHistory] =
        await Promise.all([
          apiClient.listConversations(),
          apiClient.listModels(),
          apiClient.getVoiceSettings(),
          apiClient.listVoiceSessions(new URLSearchParams({ limit: "6" })),
        ]);
      setModels(modelList);
      setVoiceSettings(loadedVoiceSettings);
      setVoiceSessions(voiceHistory.items);
      if (modelList[0]) {
        setModel(modelList[0].model);
        setProvider(modelList[0].provider);
      }
      const firstConversation = conversationList[0];
      if (firstConversation) {
        setConversations(conversationList);
        setActiveConversation(
          await apiClient.getConversation(firstConversation.id),
        );
      } else {
        const created = await apiClient.createConversation(
          response.csrf_token,
          "Grounded chat",
        );
        setConversations([created]);
        setActiveConversation(await apiClient.getConversation(created.id));
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Login failed.");
    } finally {
      setBusy(false);
    }
  }

  async function refreshConversation(conversationId = activeConversation?.id) {
    if (!conversationId) {
      return;
    }
    const detail = await apiClient.getConversation(conversationId);
    setActiveConversation(detail);
    setConversations(await apiClient.listConversations());
  }

  async function refreshVoiceSessions() {
    const history = await apiClient.listVoiceSessions(
      new URLSearchParams({ limit: "6" }),
    );
    setVoiceSessions(history.items);
  }

  async function createConversation() {
    if (!csrfToken) {
      return;
    }
    const created = await apiClient.createConversation(
      csrfToken,
      "New conversation",
    );
    setConversations([created, ...conversations]);
    setActiveConversation(await apiClient.getConversation(created.id));
    setStreamingText("");
    setStreamingCitations([]);
  }

  async function sendMessage(
    retryMessageId?: string,
    overrideContent?: string,
  ) {
    const messageContent =
      overrideContent?.trim() ||
      content.trim() ||
      activeConversation?.messages.find(
        (message) => message.id === retryMessageId,
      )?.content ||
      "";
    if (
      !csrfToken ||
      !activeConversation ||
      (!messageContent && !retryMessageId)
    ) {
      return;
    }
    setBusy(true);
    setError(null);
    setStreamingText("");
    setStreamingCitations([]);
    setUsage(null);
    setTrace(null);
    const controller = new AbortController();
    abortRef.current = controller;
    const payload = {
      content: messageContent,
      mode,
      provider: provider as StreamChatPayload["provider"],
      model: model || null,
      filters: {
        tags: tagFilter
          .split(",")
          .map((tag) => tag.trim())
          .filter(Boolean),
      },
      debug: true,
    };
    try {
      const onEvent = (event: StreamEvent) => handleStreamEvent(event);
      if (retryMessageId) {
        await apiClient.retryMessageResponse(
          retryMessageId,
          csrfToken,
          payload,
          onEvent,
          controller.signal,
        );
      } else {
        await apiClient.streamConversationResponse(
          activeConversation.id,
          csrfToken,
          payload,
          onEvent,
          controller.signal,
        );
      }
      await refreshConversation(activeConversation.id);
      await refreshVoiceSessions();
      setContent("");
      setTranscriptText("");
      setEditingTranscript(false);
    } catch (cause) {
      if (controller.signal.aborted) {
        setError(null);
      } else {
        setError(cause instanceof Error ? cause.message : "Message failed.");
      }
    } finally {
      setBusy(false);
      abortRef.current = null;
    }
  }

  function handleStreamEvent(event: StreamEvent) {
    if (event.event === "run_started") {
      setCurrentRunId(String(event.data.run_id ?? ""));
      setLastUserMessageId(String(event.data.message_id ?? ""));
      setTrace({
        request_id: event.data.request_id,
        trace_id: event.data.trace_id,
        run_id: event.data.run_id,
      });
    }
    if (event.event === "token_delta") {
      setStreamingText(
        (current) => `${current}${String(event.data.text ?? "")}`,
      );
    }
    if (event.event === "citation") {
      setStreamingCitations((current) => [...current, event.data as Citation]);
    }
    if (event.event === "usage") {
      setUsage(event.data);
    }
    if (event.event === "completed") {
      const answerText = String(event.data.answer_text ?? "");
      setUsage((event.data.usage as Record<string, unknown>) ?? null);
      setTrace({
        request_id: event.data.request_id,
        trace_id: event.data.trace_id,
        run_id: event.data.run_id,
        latency_ms: event.data.latency_ms,
        warnings: event.data.warnings,
      });
      setStreamingCitations((event.data.citations as Citation[]) ?? []);
      if (voiceSettings?.auto_speak_assistant && answerText) {
        void speakAssistant(answerText);
      }
    }
    if (event.event === "failed") {
      setError(String(event.data.detail ?? "Generation failed."));
    }
  }

  async function stopGeneration() {
    abortRef.current?.abort();
    if (csrfToken && currentRunId) {
      await apiClient.cancelRun(currentRunId, csrfToken);
    }
    setBusy(false);
  }

  async function openSource(citation: Citation) {
    const source = await apiClient.getSourceChunk(citation.chunk_id);
    setSelectedSource(source);
  }

  async function sendFeedback(rating: 1 | -1) {
    const assistant = activeConversation?.messages.findLast(
      (message) => message.role === "assistant",
    );
    if (!csrfToken || !assistant) {
      return;
    }
    await apiClient.createFeedback(csrfToken, {
      target_type: "message",
      target_id: assistant.id,
      rating,
    });
  }

  async function startRecording() {
    if (!csrfToken || !voiceSettings || voiceState === "recording") {
      return;
    }
    if (
      !navigator.mediaDevices?.getUserMedia ||
      typeof MediaRecorder === "undefined"
    ) {
      setVoiceState("error");
      setVoiceError("This browser does not support microphone recording.");
      return;
    }
    setVoiceError(null);
    setVoiceState("requesting-permission");
    cancelledRecordingRef.current = false;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = selectRecorderMime(voiceSettings.accepted_mime_types);
      const recorder = mimeType
        ? new MediaRecorder(stream, { mimeType })
        : new MediaRecorder(stream);
      mediaStreamRef.current = stream;
      mediaRecorderRef.current = recorder;
      recordingChunksRef.current = [];
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          recordingChunksRef.current.push(event.data);
        }
      };
      recorder.onstop = () => {
        void finishRecording();
      };
      recordingStartedAtRef.current = Date.now();
      recorder.start(250);
      setRecordingSeconds(0);
      setAudioLevel(0);
      setVoiceState("recording");
      setupAudioMeter(stream);
      recordingTimerRef.current = window.setInterval(() => {
        const elapsedSeconds = Math.round(
          (Date.now() - recordingStartedAtRef.current) / 1000,
        );
        setRecordingSeconds(elapsedSeconds);
        if (elapsedSeconds >= voiceSettings.max_recording_seconds) {
          stopRecording();
        }
      }, 250);
    } catch (cause) {
      cleanupRecording();
      setVoiceState("error");
      setVoiceError(
        cause instanceof Error
          ? cause.message
          : "Microphone permission was denied.",
      );
    }
  }

  function stopRecording() {
    const recorder = mediaRecorderRef.current;
    if (recorder && recorder.state !== "inactive") {
      setVoiceState("transcribing");
      recorder.stop();
    }
  }

  function cancelVoiceInteraction() {
    cancelledRecordingRef.current = true;
    const recorder = mediaRecorderRef.current;
    if (recorder && recorder.state !== "inactive") {
      recorder.stop();
    } else {
      cleanupRecording();
      setVoiceState("idle");
    }
    setTranscriptText("");
    setEditingTranscript(false);
    stopSpeechPlayback();
  }

  async function finishRecording() {
    const recorder = mediaRecorderRef.current;
    const durationMs = Math.max(Date.now() - recordingStartedAtRef.current, 0);
    const blob = new Blob(recordingChunksRef.current, {
      type: recorder?.mimeType || "audio/webm",
    });
    cleanupRecording();
    if (cancelledRecordingRef.current) {
      cancelledRecordingRef.current = false;
      setVoiceState("idle");
      return;
    }
    lastRecordingRef.current = { blob, durationMs };
    await transcribeBlob(blob, durationMs);
  }

  async function transcribeBlob(blob: Blob, durationMs: number) {
    if (!csrfToken || !voiceSettings) {
      return;
    }
    if (blob.size > voiceSettings.max_audio_bytes) {
      setVoiceState("error");
      setVoiceError("Recording exceeded the configured audio size limit.");
      return;
    }
    setVoiceState("transcribing");
    setVoiceError(null);
    try {
      const result = await apiClient.transcribeVoice(csrfToken, blob, {
        conversationId: activeConversation?.id,
        durationMs,
        filename: "voice.webm",
      });
      setTranscriptText(result.text);
      setEditingTranscript(voiceSettings.transcript_review_enabled);
      setTrace({
        request_id: result.request_id,
        trace_id: result.trace_id,
        voice_session_id: result.session_id,
        transcript_id: result.transcript_id,
      });
      setVoiceState("ready");
      await refreshVoiceSessions();
      if (!voiceSettings.transcript_review_enabled) {
        await sendMessage(undefined, result.text);
      }
    } catch (cause) {
      setVoiceState("error");
      setVoiceError(
        cause instanceof Error ? cause.message : "Voice transcription failed.",
      );
    }
  }

  async function retryTranscription() {
    if (!lastRecordingRef.current) {
      return;
    }
    await transcribeBlob(
      lastRecordingRef.current.blob,
      lastRecordingRef.current.durationMs,
    );
  }

  async function sendTranscript() {
    if (!transcriptText.trim()) {
      return;
    }
    await sendMessage(undefined, transcriptText);
    setVoiceState("idle");
  }

  function discardTranscript() {
    setTranscriptText("");
    setEditingTranscript(false);
    setVoiceState("idle");
  }

  async function updateVoiceSetting(payload: Partial<VoiceSettings>) {
    if (!csrfToken) {
      return;
    }
    const updated = await apiClient.updateVoiceSettings(csrfToken, payload);
    setVoiceSettings(updated);
  }

  async function speakAssistant(text: string) {
    if (!csrfToken || !voiceSettings || !text.trim()) {
      return;
    }
    stopSpeechPlayback();
    if (voiceSettings.tts_provider === "browser") {
      if (typeof window === "undefined" || !window.speechSynthesis) {
        setPlaybackState("error");
        setVoiceError("Browser speech synthesis is not available.");
        return;
      }
      const utterance = new SpeechSynthesisUtterance(text);
      speechUtteranceRef.current = utterance;
      utterance.onend = () => setPlaybackState("idle");
      utterance.onerror = () => setPlaybackState("error");
      setPlaybackState("playing");
      window.speechSynthesis.speak(utterance);
      return;
    }
    setPlaybackState("loading");
    try {
      const response = await apiClient.synthesizeVoice(csrfToken, {
        text,
        provider: voiceSettings.tts_provider,
        model: voiceSettings.tts_model,
        voice: voiceSettings.tts_voice,
      });
      const audio = new Audio(
        `data:${response.content_type};base64,${response.audio_base64}`,
      );
      playbackAudioRef.current = audio;
      audio.onended = () => setPlaybackState("idle");
      audio.onerror = () => setPlaybackState("error");
      setPlaybackState("playing");
      await audio.play();
    } catch (cause) {
      setPlaybackState("error");
      setVoiceError(cause instanceof Error ? cause.message : "Speech failed.");
    }
  }

  function stopSpeechPlayback() {
    if (typeof window !== "undefined" && window.speechSynthesis) {
      window.speechSynthesis.cancel();
    }
    speechUtteranceRef.current = null;
    if (playbackAudioRef.current) {
      playbackAudioRef.current.pause();
      playbackAudioRef.current.currentTime = 0;
      playbackAudioRef.current = null;
    }
    setPlaybackState("idle");
  }

  function setupAudioMeter(stream: MediaStream) {
    try {
      const context = new AudioContext();
      const analyser = context.createAnalyser();
      const source = context.createMediaStreamSource(stream);
      analyser.fftSize = 128;
      source.connect(analyser);
      analyserRef.current = analyser;
      audioContextRef.current = context;
      const data = new Uint8Array(analyser.frequencyBinCount);
      const tick = () => {
        analyser.getByteFrequencyData(data);
        const average =
          data.reduce((sum, value) => sum + value, 0) /
          Math.max(data.length, 1);
        setAudioLevel(average / 255);
        animationFrameRef.current = window.requestAnimationFrame(tick);
      };
      tick();
    } catch {
      setAudioLevel(0);
    }
  }

  function cleanupRecording() {
    if (recordingTimerRef.current) {
      window.clearInterval(recordingTimerRef.current);
      recordingTimerRef.current = null;
    }
    if (animationFrameRef.current) {
      window.cancelAnimationFrame(animationFrameRef.current);
      animationFrameRef.current = null;
    }
    audioContextRef.current?.close().catch(() => undefined);
    audioContextRef.current = null;
    analyserRef.current = null;
    mediaStreamRef.current?.getTracks().forEach((track) => track.stop());
    mediaStreamRef.current = null;
    mediaRecorderRef.current = null;
    recordingChunksRef.current = [];
    setAudioLevel(0);
  }

  const activeMessages = activeConversation?.messages ?? [];
  const maxRecordingSeconds = voiceSettings?.max_recording_seconds ?? 60;
  const latestAssistantText =
    streamingText ||
    [...activeMessages]
      .reverse()
      .find((message) => message.role === "assistant")?.content ||
    "";

  return (
    <div className="app-shell">
      <aside className="sidebar chat-sidebar" aria-label="Primary navigation">
        <div className="brand">
          <div className="brand-mark" aria-hidden="true">
            <BrainCircuit size={23} strokeWidth={1.8} />
          </div>
          <div>
            <p className="brand-title">Loomi-Brain</p>
            <p className="brand-subtitle">Cited chat</p>
          </div>
        </div>
        <nav>
          <ul className="nav-list">
            <li>
              <Link className="nav-link" href="/">
                <Home size={18} aria-hidden="true" />
                <span>Home</span>
              </Link>
            </li>
            <li>
              <Link className="nav-link" href="/knowledge">
                <Library size={18} aria-hidden="true" />
                <span>Knowledge</span>
              </Link>
            </li>
            <li>
              <Link className="nav-link" href="/search">
                <Search size={18} aria-hidden="true" />
                <span>Search</span>
              </Link>
            </li>
            <li>
              <Link className="nav-link" href="/chat" aria-current="page">
                <MessageSquare size={18} aria-hidden="true" />
                <span>Chat</span>
              </Link>
            </li>
            <li>
              <Link className="nav-link" href="/runs">
                <Workflow size={18} aria-hidden="true" />
                <span>Runs</span>
              </Link>
            </li>
          </ul>
        </nav>
        {csrfToken ? (
          <section className="conversation-list" aria-label="Conversations">
            <button
              className="command-button"
              type="button"
              onClick={() => void createConversation()}
            >
              New Chat
            </button>
            {conversations.map((conversation) => (
              <button
                key={conversation.id}
                type="button"
                aria-pressed={activeConversation?.id === conversation.id}
                onClick={() => void refreshConversation(conversation.id)}
              >
                {conversation.title}
              </button>
            ))}
          </section>
        ) : null}
      </aside>

      <main className="main chat-main">
        {!csrfToken ? (
          <section className="auth-panel" aria-labelledby="chat-auth-title">
            <h1 id="chat-auth-title">Owner Login</h1>
            <label>
              Email
              <input
                value={email}
                onChange={(event) => setEmail(event.target.value)}
              />
            </label>
            <label>
              Password
              <input
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </label>
            <button
              className="command-button"
              type="button"
              disabled={busy}
              onClick={handleLogin}
            >
              <LogIn size={18} aria-hidden="true" />
              Sign In
            </button>
            {error ? <p className="form-error">{error}</p> : null}
          </section>
        ) : (
          <div className="chat-grid">
            <section className="chat-thread" aria-label="Conversation">
              <div className="section-header">
                <div>
                  <p className="eyebrow">Grounded workspace</p>
                  <h1>{activeConversation?.title ?? "Chat"}</h1>
                </div>
                <div className="chat-status-stack">
                  <VoiceModeToggle
                    enabled={voiceEnabled}
                    onChange={setVoiceEnabled}
                  />
                  <StatusPill tone={busy ? "warn" : "good"}>
                    {busy ? "Streaming" : "Ready"}
                  </StatusPill>
                </div>
              </div>
              <div className="message-list">
                {activeMessages.length === 0 && !streamingText ? (
                  <div className="empty-state">
                    <MessageSquare size={22} aria-hidden="true" />
                    <p>Ask a question after uploading synthetic documents.</p>
                  </div>
                ) : null}
                {activeMessages.map((message) => (
                  <article
                    className={`chat-message chat-message--${message.role}`}
                    key={message.id}
                  >
                    <div className="message-role">{message.role}</div>
                    {message.role === "assistant" ? (
                      <SafeMarkdown value={message.content} />
                    ) : (
                      <p>{message.content}</p>
                    )}
                    {message.citations.length > 0 ? (
                      <CitationRow
                        citations={message.citations}
                        onOpen={openSource}
                      />
                    ) : null}
                  </article>
                ))}
                {streamingText ? (
                  <article className="chat-message chat-message--assistant">
                    <div className="message-role">assistant</div>
                    <SafeMarkdown value={streamingText} />
                    <CitationRow
                      citations={streamingCitations}
                      onOpen={openSource}
                    />
                  </article>
                ) : null}
              </div>
              <div className="composer">
                {voiceEnabled && voiceSettings ? (
                  <section className="voice-panel" aria-label="Voice mode">
                    <div className="voice-panel__head">
                      <div>
                        <p className="eyebrow">Voice mode</p>
                        <VoiceProviderBadge
                          label="STT"
                          option={{
                            provider: voiceSettings.stt_provider,
                            model: voiceSettings.stt_model,
                            configured:
                              voiceSettings.stt_provider === "mock" ||
                              (voiceSettings.stt_provider === "openai"
                                ? voiceSettings.openai_configured &&
                                  voiceSettings.cloud_enabled
                                : voiceSettings.local_stt_configured),
                            cloud: voiceSettings.stt_provider === "openai",
                            demo: voiceSettings.stt_provider === "mock",
                          }}
                        />
                      </div>
                      <div className="voice-panel__actions">
                        <VoiceInputButton
                          state={voiceState}
                          mode={captureMode}
                          disabled={busy || voiceState === "transcribing"}
                          icon={<Mic size={17} />}
                          onToggle={() => {
                            if (voiceState === "recording") {
                              stopRecording();
                            } else {
                              void startRecording();
                            }
                          }}
                          onPressStart={() => void startRecording()}
                          onPressEnd={stopRecording}
                        />
                        <button type="button" onClick={cancelVoiceInteraction}>
                          <Square size={17} aria-hidden="true" />
                          Cancel
                        </button>
                      </div>
                    </div>
                    <VoiceRecorder
                      state={voiceState}
                      elapsedSeconds={recordingSeconds}
                      maxSeconds={maxRecordingSeconds}
                      level={audioLevel}
                    >
                      <MicrophonePermissionNotice state={voiceState} />
                      <AudioPrivacyNotice
                        provider={voiceSettings.stt_provider}
                        retainRawAudio={voiceSettings.retain_raw_audio}
                      />
                    </VoiceRecorder>
                    {transcriptText ? (
                      editingTranscript ? (
                        <TranscriptEditor
                          value={transcriptText}
                          onChange={setTranscriptText}
                          onCancel={() => setEditingTranscript(false)}
                          onSend={() => void sendTranscript()}
                        />
                      ) : (
                        <TranscriptPreview
                          text={transcriptText}
                          editable={voiceSettings.transcript_review_enabled}
                          onEdit={() => setEditingTranscript(true)}
                          onRetry={() => void retryTranscription()}
                          onDiscard={discardTranscript}
                          onSend={() => void sendTranscript()}
                        />
                      )
                    ) : null}
                    <div className="voice-hint-row">
                      <span>Ctrl/⌘ Shift V</span>
                      <span>
                        {captureMode === "push"
                          ? "hold button"
                          : "click to record"}
                      </span>
                    </div>
                  </section>
                ) : null}
                <textarea
                  aria-label="Message"
                  value={content}
                  onChange={(event) => setContent(event.target.value)}
                  onKeyDown={(event) => {
                    if (
                      (event.metaKey || event.ctrlKey) &&
                      event.shiftKey &&
                      event.key.toLowerCase() === "v"
                    ) {
                      event.preventDefault();
                      if (voiceState === "recording") {
                        stopRecording();
                      } else {
                        void startRecording();
                      }
                    }
                    if (
                      (event.metaKey || event.ctrlKey) &&
                      event.key === "Enter"
                    ) {
                      void sendMessage();
                    }
                  }}
                />
                <div className="composer-actions">
                  <button
                    className="command-button"
                    type="button"
                    disabled={busy}
                    onClick={() => void sendMessage()}
                  >
                    {busy ? (
                      <Loader2 size={18} aria-hidden="true" />
                    ) : (
                      <Send size={18} aria-hidden="true" />
                    )}
                    Send
                  </button>
                  <button
                    type="button"
                    disabled={!busy}
                    onClick={() => void stopGeneration()}
                  >
                    <Square size={17} aria-hidden="true" />
                    Stop
                  </button>
                  <button
                    type="button"
                    disabled={!lastUserMessageId || busy}
                    onClick={() =>
                      void sendMessage(lastUserMessageId ?? undefined)
                    }
                  >
                    <RotateCcw size={17} aria-hidden="true" />
                    Retry
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      void navigator.clipboard.writeText(streamingText)
                    }
                  >
                    <Clipboard size={17} aria-hidden="true" />
                    Copy
                  </button>
                </div>
                {error ? <p className="form-error">{error}</p> : null}
                {voiceError ? <p className="form-error">{voiceError}</p> : null}
              </div>
            </section>

            <aside
              className="chat-inspector"
              aria-label="Chat controls and source preview"
            >
              <section>
                <h2 className="section-title">Run Controls</h2>
                <label>
                  Model
                  <select
                    value={`${provider}:${model}`}
                    onChange={(event) => {
                      const [nextProvider, nextModel] =
                        event.target.value.split(":");
                      setProvider(nextProvider ?? "mock");
                      setModel(nextModel ?? "");
                    }}
                  >
                    {models.map((item) => (
                      <option
                        key={`${item.provider}-${item.model}`}
                        value={`${item.provider}:${item.model}`}
                      >
                        {item.provider} · {item.model}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Search mode
                  <select
                    value={mode}
                    onChange={(event) =>
                      setMode(event.target.value as SearchMode)
                    }
                  >
                    <option value="hybrid">Hybrid</option>
                    <option value="lexical">Lexical</option>
                    <option value="semantic">Semantic</option>
                  </select>
                </label>
                <label>
                  Tags
                  <input
                    value={tagFilter}
                    onChange={(event) => setTagFilter(event.target.value)}
                  />
                </label>
                <div className="feedback-row">
                  <button type="button" onClick={() => void sendFeedback(1)}>
                    <ThumbsUp size={17} aria-hidden="true" />
                    Helpful
                  </button>
                  <button type="button" onClick={() => void sendFeedback(-1)}>
                    <ThumbsDown size={17} aria-hidden="true" />
                    Not Helpful
                  </button>
                </div>
              </section>

              {voiceSettings ? (
                <section>
                  <h2 className="section-title">
                    <Settings2 size={17} aria-hidden="true" />
                    Voice
                  </h2>
                  <VoiceSettingsPanel
                    stt={{
                      provider: voiceSettings.stt_provider,
                      model: voiceSettings.stt_model,
                      configured:
                        voiceSettings.stt_provider === "mock" ||
                        (voiceSettings.stt_provider === "openai"
                          ? voiceSettings.openai_configured &&
                            voiceSettings.cloud_enabled
                          : voiceSettings.local_stt_configured),
                      cloud: voiceSettings.stt_provider === "openai",
                      demo: voiceSettings.stt_provider === "mock",
                    }}
                    tts={{
                      provider: voiceSettings.tts_provider,
                      model: voiceSettings.tts_model,
                      configured:
                        voiceSettings.tts_provider === "browser" ||
                        voiceSettings.tts_provider === "mock" ||
                        (voiceSettings.tts_provider === "openai"
                          ? voiceSettings.openai_configured &&
                            voiceSettings.cloud_enabled
                          : voiceSettings.local_tts_configured),
                      cloud: voiceSettings.tts_provider === "openai",
                      demo: voiceSettings.tts_provider === "mock",
                    }}
                    transcriptReviewEnabled={
                      voiceSettings.transcript_review_enabled
                    }
                    autoSpeakAssistant={voiceSettings.auto_speak_assistant}
                    retainRawAudio={voiceSettings.retain_raw_audio}
                    onTranscriptReviewChange={(enabled) =>
                      void updateVoiceSetting({
                        transcript_review_enabled: enabled,
                      })
                    }
                    onAutoSpeakChange={(enabled) =>
                      void updateVoiceSetting({
                        auto_speak_assistant: enabled,
                      })
                    }
                    onRetainAudioChange={(enabled) =>
                      void updateVoiceSetting({
                        retain_raw_audio: enabled,
                        retention_days: enabled
                          ? Math.max(voiceSettings.retention_days, 1)
                          : 0,
                      })
                    }
                  />
                  <label>
                    Capture
                    <select
                      value={captureMode}
                      onChange={(event) =>
                        setCaptureMode(event.target.value as "click" | "push")
                      }
                    >
                      <option value="click">Click to record</option>
                      <option value="push">Push to talk</option>
                    </select>
                  </label>
                  <label>
                    Speech to text
                    <select
                      value={voiceSettings.stt_provider}
                      onChange={(event) => {
                        const nextProvider = event.target
                          .value as VoiceSettings["stt_provider"];
                        void updateVoiceSetting({
                          stt_provider: nextProvider,
                          stt_model:
                            nextProvider === "openai"
                              ? "gpt-4o-mini-transcribe"
                              : nextProvider === "local-compatible"
                                ? "whisper-1"
                                : "loomi-mock-transcribe-v1",
                        });
                      }}
                    >
                      <option value="mock">Mock demo</option>
                      <option value="openai">OpenAI cloud</option>
                      <option value="local-compatible">Local compatible</option>
                    </select>
                  </label>
                  <label>
                    Text to speech
                    <select
                      value={voiceSettings.tts_provider}
                      onChange={(event) => {
                        const nextProvider = event.target
                          .value as VoiceSettings["tts_provider"];
                        void updateVoiceSetting({
                          tts_provider: nextProvider,
                          tts_model:
                            nextProvider === "openai"
                              ? "gpt-4o-mini-tts"
                              : nextProvider === "local-compatible"
                                ? "tts-1"
                                : nextProvider === "mock"
                                  ? "loomi-mock-tts-v1"
                                  : "loomi-browser-speech-synthesis",
                        });
                      }}
                    >
                      <option value="browser">Browser</option>
                      <option value="mock">Mock audio</option>
                      <option value="openai">OpenAI cloud</option>
                      <option value="local-compatible">Local compatible</option>
                    </select>
                  </label>
                  <label>
                    Voice
                    <select
                      value={voiceSettings.tts_voice}
                      onChange={(event) =>
                        void updateVoiceSetting({
                          tts_voice: event.target.value,
                        })
                      }
                    >
                      {voiceSettings.allowed_tts_voices.map((voice) => (
                        <option key={voice} value={voice}>
                          {voice}
                        </option>
                      ))}
                    </select>
                  </label>
                  <SpeechPlaybackControls
                    state={playbackState}
                    onPlay={() => void speakAssistant(latestAssistantText)}
                    onStop={stopSpeechPlayback}
                  />
                  <button
                    type="button"
                    disabled={!latestAssistantText}
                    onClick={() => void speakAssistant(latestAssistantText)}
                  >
                    <Volume2 size={17} aria-hidden="true" />
                    Speak Answer
                  </button>
                </section>
              ) : null}

              {voiceSessions.length > 0 ? (
                <section>
                  <h2 className="section-title">Voice Sessions</h2>
                  <VoiceSessionTimeline
                    items={voiceSessions.map((item) => ({
                      id: item.id,
                      status: item.status,
                      provider: item.stt_provider,
                      model: item.stt_model,
                      createdAt: item.created_at,
                      durationMs: item.duration_ms,
                      audioSizeBytes: item.audio_size_bytes,
                      traceId: item.trace_id,
                    }))}
                  />
                </section>
              ) : null}

              <section>
                <h2 className="section-title">Trace</h2>
                <pre className="debug-block">
                  {JSON.stringify({ usage, trace }, null, 2)}
                </pre>
                {currentRunId ? (
                  <Link className="trace-link" href="/runs">
                    Open run inspector
                  </Link>
                ) : null}
              </section>

              <section>
                <h2 className="section-title">Source</h2>
                {selectedSource ? (
                  <article className="source-panel">
                    <p className="item-title">
                      {selectedSource.document_title}
                    </p>
                    <p className="item-meta">
                      v{selectedSource.document_version} ·{" "}
                      {selectedSource.chunk_id}
                    </p>
                    <pre>{selectedSource.excerpt}</pre>
                  </article>
                ) : (
                  <div className="empty-state">
                    <Library size={22} aria-hidden="true" />
                    <p>Select a citation to preview its stored chunk.</p>
                  </div>
                )}
              </section>
            </aside>
          </div>
        )}
      </main>
    </div>
  );
}

function CitationRow({
  citations,
  onOpen,
}: {
  citations: Citation[];
  onOpen: (citation: Citation) => Promise<void>;
}) {
  if (citations.length === 0) {
    return null;
  }
  return (
    <div className="citation-row">
      {citations.map((citation) => (
        <button
          key={`${citation.chunk_id}-${citation.citation_id ?? "citation"}`}
          type="button"
          onClick={() => void onOpen(citation)}
        >
          {citation.document_title} · chunk {citation.chunk_id.slice(0, 8)}
        </button>
      ))}
    </div>
  );
}

function resolveApiBase() {
  if (typeof window === "undefined") {
    return API_BASE;
  }
  try {
    const configured = new URL(API_BASE);
    const currentHost = window.location.hostname;
    const loopbackHosts = new Set(["localhost", "127.0.0.1"]);
    if (
      loopbackHosts.has(configured.hostname) &&
      loopbackHosts.has(currentHost)
    ) {
      configured.hostname = currentHost;
      return configured.origin;
    }
  } catch {
    return API_BASE;
  }
  return API_BASE;
}

function selectRecorderMime(acceptedTypes: string[]) {
  const candidates = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/mp4",
    "audio/ogg;codecs=opus",
    "audio/wav",
  ];
  return candidates.find((candidate) => {
    const baseType = candidate.split(";", 1)[0];
    if (!baseType) {
      return false;
    }
    return (
      acceptedTypes.includes(baseType) &&
      MediaRecorder.isTypeSupported(candidate)
    );
  });
}
