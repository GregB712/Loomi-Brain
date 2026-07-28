"use client";

import {
  createLoomiClient,
  type DocumentListResponse,
  type SearchMode,
  type SearchResponse,
} from "@loomi/contracts";
import { StatusPill } from "@loomi/ui";
import {
  BrainCircuit,
  Filter,
  Home,
  Library,
  Loader2,
  LogIn,
  MessageSquare,
  Search,
  SlidersHorizontal,
} from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export function SearchClient() {
  const apiClient = useMemo(() => createLoomiClient(resolveApiBase()), []);
  const [email, setEmail] = useState("owner@loomi.local");
  const [password, setPassword] = useState("");
  const [csrfToken, setCsrfToken] = useState<string | null>(null);
  const [query, setQuery] = useState("reciprocal rank fusion");
  const [mode, setMode] = useState<SearchMode>("hybrid");
  const [tagFilter, setTagFilter] = useState("");
  const [documentId, setDocumentId] = useState("");
  const [debug, setDebug] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [documents, setDocuments] = useState<DocumentListResponse | null>(null);
  const [results, setResults] = useState<SearchResponse | null>(null);

  async function handleLogin() {
    setBusy(true);
    setError(null);
    try {
      const response = await apiClient.login(email, password);
      setCsrfToken(response.csrf_token);
      const list = await apiClient.listDocuments(
        new URLSearchParams({ status: "completed", limit: "100", offset: "0" }),
      );
      setDocuments(list);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Login failed.");
    } finally {
      setBusy(false);
    }
  }

  async function handleSearch() {
    setBusy(true);
    setError(null);
    try {
      const response = await apiClient.search({
        query,
        mode,
        debug,
        limit: 12,
        min_score: mode === "semantic" ? 0.05 : 0,
        filters: {
          document_ids: documentId ? [documentId] : [],
          tags: tagFilter
            .split(",")
            .map((tag) => tag.trim())
            .filter(Boolean),
        },
      });
      setResults(response);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Search failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="Primary navigation">
        <div className="brand">
          <div className="brand-mark" aria-hidden="true">
            <BrainCircuit size={23} strokeWidth={1.8} />
          </div>
          <div>
            <p className="brand-title">Loomi-Brain</p>
            <p className="brand-subtitle">Search</p>
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
              <Link className="nav-link" href="/search" aria-current="page">
                <Search size={18} aria-hidden="true" />
                <span>Search</span>
              </Link>
            </li>
            <li>
              <Link className="nav-link" href="/chat">
                <MessageSquare size={18} aria-hidden="true" />
                <span>Chat</span>
              </Link>
            </li>
          </ul>
        </nav>
      </aside>

      <main className="main search-main">
        <header className="knowledge-header">
          <div>
            <p className="eyebrow">Hybrid retrieval</p>
            <h1>Search the knowledge base.</h1>
            <p className="topbar-copy">
              Compare lexical, semantic, and hybrid retrieval with provenance,
              bounded results, and owner-only debug scores.
            </p>
          </div>
          <section className="environment-panel" aria-label="Search status">
            <p className="panel-label">Mode</p>
            <p className="panel-value">{mode}</p>
            <StatusPill tone="good">Phase 3</StatusPill>
          </section>
        </header>

        {!csrfToken ? (
          <section className="auth-panel" aria-labelledby="search-auth-title">
            <h2 id="search-auth-title">Owner Login</h2>
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
          <div className="search-layout">
            <section
              className="search-controls"
              aria-labelledby="search-controls-title"
            >
              <div className="section-header">
                <h2 className="section-title" id="search-controls-title">
                  Query
                </h2>
                <SlidersHorizontal size={18} aria-hidden="true" />
              </div>
              <label>
                Search
                <textarea
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                />
              </label>
              <div className="segmented" role="group" aria-label="Search mode">
                {(["lexical", "semantic", "hybrid"] as const).map((item) => (
                  <button
                    key={item}
                    type="button"
                    aria-pressed={mode === item}
                    onClick={() => setMode(item)}
                  >
                    {item}
                  </button>
                ))}
              </div>
              <label>
                <Filter size={16} aria-hidden="true" />
                <select
                  value={documentId}
                  onChange={(event) => setDocumentId(event.target.value)}
                >
                  <option value="">All documents</option>
                  {documents?.items.map((document) => (
                    <option value={document.id} key={document.id}>
                      {document.title}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Tags
                <input
                  placeholder="research, notes"
                  value={tagFilter}
                  onChange={(event) => setTagFilter(event.target.value)}
                />
              </label>
              <label className="toggle-row">
                <input
                  type="checkbox"
                  checked={debug}
                  onChange={(event) => setDebug(event.target.checked)}
                />
                Owner debug
              </label>
              <button
                className="command-button"
                type="button"
                disabled={busy}
                onClick={handleSearch}
              >
                {busy ? (
                  <Loader2 size={18} aria-hidden="true" />
                ) : (
                  <Search size={18} aria-hidden="true" />
                )}
                Search
              </button>
              {error ? <p className="form-error">{error}</p> : null}
            </section>

            <section className="search-results" aria-live="polite">
              <div className="section-header">
                <h2 className="section-title">Results</h2>
                {results ? (
                  <StatusPill tone="neutral">{`${results.latency_ms}ms`}</StatusPill>
                ) : null}
              </div>
              {!results ? (
                <div className="empty-state">
                  <Search size={22} aria-hidden="true" />
                  <p>Run a query to inspect ranked chunks and provenance.</p>
                </div>
              ) : results.items.length === 0 ? (
                <div className="empty-state">
                  <Search size={22} aria-hidden="true" />
                  <p>No chunks met the current search filters.</p>
                </div>
              ) : (
                <div className="result-list">
                  {results.items.map((item) => (
                    <article className="result-card" key={item.chunk_id}>
                      <div className="result-card__head">
                        <div>
                          <h2>{item.document_title}</h2>
                          <p className="item-meta">
                            Chunk {item.ordinal + 1} · v{item.document_version}{" "}
                            · {item.source_kind}
                          </p>
                        </div>
                        <StatusPill tone="good">
                          {`${Math.round(item.score * 100)}%`}
                        </StatusPill>
                      </div>
                      <p className="result-excerpt">
                        {highlight(item.excerpt, query)}
                      </p>
                      <div className="score-grid">
                        <span>Lexical {formatScore(item.lexical_score)}</span>
                        <span>Semantic {formatScore(item.semantic_score)}</span>
                        <span>{item.source_preview_locator}</span>
                      </div>
                      {debug && item.debug ? (
                        <pre className="debug-block">
                          {JSON.stringify(item.debug, null, 2)}
                        </pre>
                      ) : null}
                    </article>
                  ))}
                </div>
              )}
            </section>
          </div>
        )}
      </main>
    </div>
  );
}

function highlight(text: string, query: string) {
  const terms = query
    .split(/\s+/)
    .map((term) => term.replace(/[^a-zA-Z0-9_-]/g, "").toLowerCase())
    .filter((term) => term.length > 2);
  if (terms.length === 0) {
    return text;
  }
  const pattern = new RegExp(`(${terms.join("|")})`, "ig");
  return text
    .split(pattern)
    .map((part, index) =>
      terms.includes(part.toLowerCase()) ? (
        <mark key={`${part}-${index}`}>{part}</mark>
      ) : (
        part
      ),
    );
}

function formatScore(value: number | null) {
  return value === null ? "n/a" : `${Math.round(value * 100)}%`;
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
