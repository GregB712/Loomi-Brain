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
} from "@loomi/contracts";
import { StatusPill } from "@loomi/ui";
import {
  BrainCircuit,
  Clipboard,
  Home,
  Library,
  Loader2,
  LogIn,
  MessageSquare,
  RotateCcw,
  Search,
  Send,
  Square,
  ThumbsDown,
  ThumbsUp,
} from "lucide-react";
import Link from "next/link";
import { useMemo, useRef, useState } from "react";
import { SafeMarkdown } from "./safe-markdown";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export function ChatClient() {
  const apiClient = useMemo(() => createLoomiClient(resolveApiBase()), []);
  const abortRef = useRef<AbortController | null>(null);
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

  async function handleLogin() {
    setBusy(true);
    setError(null);
    try {
      const response = await apiClient.login(email, password);
      setCsrfToken(response.csrf_token);
      setPassword("");
      const [conversationList, modelList] = await Promise.all([
        apiClient.listConversations(),
        apiClient.listModels(),
      ]);
      setModels(modelList);
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

  async function sendMessage(retryMessageId?: string) {
    if (
      !csrfToken ||
      !activeConversation ||
      (!content.trim() && !retryMessageId)
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
      content: content.trim(),
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
      setContent("");
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
      setUsage((event.data.usage as Record<string, unknown>) ?? null);
      setTrace({
        request_id: event.data.request_id,
        trace_id: event.data.trace_id,
        run_id: event.data.run_id,
        latency_ms: event.data.latency_ms,
        warnings: event.data.warnings,
      });
      setStreamingCitations((event.data.citations as Citation[]) ?? []);
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

  const activeMessages = activeConversation?.messages ?? [];

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
                <StatusPill tone={busy ? "warn" : "good"}>
                  {busy ? "Streaming" : "Ready"}
                </StatusPill>
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
                <textarea
                  aria-label="Message"
                  value={content}
                  onChange={(event) => setContent(event.target.value)}
                  onKeyDown={(event) => {
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

              <section>
                <h2 className="section-title">Trace</h2>
                <pre className="debug-block">
                  {JSON.stringify({ usage, trace }, null, 2)}
                </pre>
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
