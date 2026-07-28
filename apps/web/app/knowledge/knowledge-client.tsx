"use client";

import {
  createLoomiClient,
  type DocumentDetail,
  type DocumentListResponse,
  type DocumentStatus,
  type JobDetail,
  type PreviewResponse,
  type UploadResponse,
} from "@loomi/contracts";
import { StatusPill } from "@loomi/ui";
import {
  AlertTriangle,
  CheckCircle2,
  FileText,
  Filter,
  Home,
  Library,
  ListRestart,
  Loader2,
  LogIn,
  MessageSquare,
  RefreshCw,
  Search,
  ShieldCheck,
  Tags,
  Trash2,
  Upload,
  Workflow,
  XCircle,
} from "lucide-react";
import Link from "next/link";
import {
  type ChangeEvent,
  type DragEvent,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";
const PAGE_SIZE = 10;

const statusTone: Record<DocumentStatus, "neutral" | "good" | "warn" | "bad"> =
  {
    queued: "neutral",
    validating: "neutral",
    scanning: "warn",
    extracting: "neutral",
    normalizing: "neutral",
    chunking: "neutral",
    embedding: "neutral",
    indexing: "neutral",
    completed: "good",
    failed: "bad",
    cancelled: "warn",
  };

export function KnowledgeClient() {
  const apiClient = useMemo(() => createLoomiClient(resolveApiBase()), []);
  const [email, setEmail] = useState("owner@loomi.local");
  const [password, setPassword] = useState("");
  const [csrfToken, setCsrfToken] = useState<string | null>(null);
  const [authError, setAuthError] = useState<string | null>(null);
  const [documents, setDocuments] = useState<DocumentListResponse>({
    items: [],
    total: 0,
    limit: PAGE_SIZE,
    offset: 0,
  });
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState("created_desc");
  const [offset, setOffset] = useState(0);
  const [files, setFiles] = useState<File[]>([]);
  const [uploadResult, setUploadResult] = useState<UploadResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<DocumentDetail | null>(null);
  const [preview, setPreview] = useState<PreviewResponse | null>(null);
  const [tagsInput, setTagsInput] = useState("");
  const [message, setMessage] = useState<string | null>(null);

  const isAuthenticated = csrfToken !== null;
  const selectedDocument = useMemo(
    () =>
      documents.items.find((document) => document.id === selectedId) ?? null,
    [documents.items, selectedId],
  );

  const refreshDocuments = useCallback(async () => {
    if (!csrfToken) {
      return;
    }
    const params = new URLSearchParams({
      limit: String(PAGE_SIZE),
      offset: String(offset),
      sort,
    });
    if (statusFilter) {
      params.set("status", statusFilter);
    }
    if (query.trim()) {
      params.set("q", query.trim());
    }
    const data = await apiClient.listDocuments(params);
    setDocuments(data);
    const firstDocument = data.items[0];
    if (!selectedId && firstDocument) {
      setSelectedId(firstDocument.id);
    }
  }, [apiClient, csrfToken, offset, query, selectedId, sort, statusFilter]);

  const loadSelectedDocument = useCallback(async () => {
    if (!csrfToken || !selectedId) {
      setDetail(null);
      setPreview(null);
      return;
    }
    const [nextDetail, nextPreview] = await Promise.all([
      apiClient.getDocument(selectedId),
      apiClient.previewDocument(selectedId),
    ]);
    setDetail(nextDetail);
    setPreview(nextPreview);
    setTagsInput(nextDetail.tag_names.join(", "));
  }, [apiClient, csrfToken, selectedId]);

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      void refreshDocuments().catch((error: unknown) => {
        setMessage(
          error instanceof Error ? error.message : "Could not load documents.",
        );
      });
    }, 0);
    return () => window.clearTimeout(timeout);
  }, [refreshDocuments]);

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      void loadSelectedDocument().catch((error: unknown) => {
        setMessage(
          error instanceof Error
            ? error.message
            : "Could not load document preview.",
        );
      });
    }, 0);
    return () => window.clearTimeout(timeout);
  }, [loadSelectedDocument]);

  useEffect(() => {
    if (!csrfToken) {
      return undefined;
    }
    const interval = window.setInterval(() => {
      void refreshDocuments();
      void loadSelectedDocument();
    }, 3500);
    return () => window.clearInterval(interval);
  }, [csrfToken, loadSelectedDocument, refreshDocuments]);

  async function handleLogin() {
    setAuthError(null);
    setBusy(true);
    try {
      const response = await apiClient.login(email, password);
      setCsrfToken(response.csrf_token);
      setPassword("");
      setMessage("Owner session established.");
      await refreshDocuments();
    } catch (error) {
      setAuthError(error instanceof Error ? error.message : "Login failed.");
    } finally {
      setBusy(false);
    }
  }

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    setFiles(Array.from(event.target.files ?? []));
  }

  function handleDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setFiles(Array.from(event.dataTransfer.files));
  }

  async function handleUpload() {
    if (!csrfToken || files.length === 0) {
      return;
    }
    setBusy(true);
    setUploadResult(null);
    setMessage(null);
    try {
      const result = await apiClient.uploadDocuments(
        files,
        csrfToken,
        crypto.randomUUID(),
      );
      setUploadResult(result);
      setFiles([]);
      await refreshDocuments();
      const firstAccepted = result.accepted[0];
      if (firstAccepted) {
        setSelectedId(firstAccepted.document_id);
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Upload failed.");
    } finally {
      setBusy(false);
    }
  }

  async function handleDocumentAction(action: "retry" | "reindex" | "delete") {
    if (!csrfToken || !selectedId) {
      return;
    }
    if (
      action === "delete" &&
      !window.confirm("Delete this document and derived data?")
    ) {
      return;
    }
    setBusy(true);
    try {
      if (action === "delete") {
        await apiClient.deleteDocument(selectedId, csrfToken);
        setSelectedId(null);
        setDetail(null);
        setPreview(null);
        setMessage("Document deleted.");
      } else {
        if (action === "retry") {
          await apiClient.retryDocument(
            selectedId,
            csrfToken,
            crypto.randomUUID(),
          );
        } else {
          await apiClient.reindexDocument(
            selectedId,
            csrfToken,
            crypto.randomUUID(),
          );
        }
        setMessage(action === "retry" ? "Retry queued." : "Re-index queued.");
      }
      await refreshDocuments();
      await loadSelectedDocument();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Action failed.");
    } finally {
      setBusy(false);
    }
  }

  async function handleSaveTags() {
    if (!csrfToken || !selectedId) {
      return;
    }
    const tags = tagsInput
      .split(",")
      .map((tag) => tag.trim())
      .filter(Boolean);
    await apiClient.updateTags(selectedId, csrfToken, tags);
    setMessage("Tags updated.");
    await refreshDocuments();
    await loadSelectedDocument();
  }

  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="Primary navigation">
        <div className="brand">
          <div className="brand-mark" aria-hidden="true">
            <Library size={23} strokeWidth={1.8} />
          </div>
          <div>
            <p className="brand-title">Loomi-Brain</p>
            <p className="brand-subtitle">Knowledge library</p>
          </div>
        </div>
        <nav>
          <ul className="nav-list">
            <li>
              <Link className="nav-link" href="/">
                <Home size={18} strokeWidth={1.8} aria-hidden="true" />
                <span>Home</span>
              </Link>
            </li>
            <li>
              <Link className="nav-link" href="/knowledge" aria-current="page">
                <Library size={18} strokeWidth={1.8} aria-hidden="true" />
                <span>Knowledge</span>
              </Link>
            </li>
            <li>
              <Link className="nav-link" href="/search">
                <Search size={18} strokeWidth={1.8} aria-hidden="true" />
                <span>Search</span>
              </Link>
            </li>
            <li>
              <Link className="nav-link" href="/chat">
                <MessageSquare size={18} strokeWidth={1.8} aria-hidden="true" />
                <span>Chat</span>
              </Link>
            </li>
            <li>
              <Link className="nav-link" href="/runs">
                <Workflow size={18} strokeWidth={1.8} aria-hidden="true" />
                <span>Runs</span>
              </Link>
            </li>
          </ul>
        </nav>
      </aside>

      <main className="main knowledge-main">
        <header className="knowledge-header">
          <div>
            <p className="eyebrow">Document intelligence</p>
            <h1>Knowledge Library</h1>
            <p className="topbar-copy">
              Upload synthetic documents, watch ingestion progress, inspect
              provenance, and manage derived data under the owner boundary.
            </p>
          </div>
          <section className="environment-panel" aria-label="Ingestion status">
            <p className="panel-label">Pipeline</p>
            <p className="panel-value">Phase 2</p>
            <StatusPill tone="good">Upload Ready</StatusPill>
          </section>
        </header>

        {!isAuthenticated ? (
          <section className="auth-panel" aria-labelledby="auth-title">
            <div>
              <h2 id="auth-title">Owner Login</h2>
              <p className="item-meta">
                Mutating document actions require the API session cookie and
                CSRF token.
              </p>
            </div>
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
            {authError ? <p className="form-error">{authError}</p> : null}
            <button
              className="command-button"
              type="button"
              onClick={handleLogin}
              disabled={busy}
            >
              <LogIn size={18} aria-hidden="true" />
              Sign In
            </button>
          </section>
        ) : (
          <div className="knowledge-grid">
            <section className="upload-panel" aria-labelledby="upload-title">
              <div className="section-header">
                <h2 className="section-title" id="upload-title">
                  Upload
                </h2>
                <Upload size={18} strokeWidth={1.8} aria-hidden="true" />
              </div>
              <label
                className="drop-zone"
                onDragOver={(event) => event.preventDefault()}
                onDrop={handleDrop}
              >
                <input multiple type="file" onChange={handleFileChange} />
                <FileText size={24} strokeWidth={1.8} aria-hidden="true" />
                <span>
                  {files.length
                    ? `${files.length} file(s) selected`
                    : "Choose or drop files"}
                </span>
              </label>
              <div className="upload-actions">
                <button
                  className="command-button"
                  type="button"
                  disabled={busy || files.length === 0}
                  onClick={handleUpload}
                >
                  {busy ? (
                    <Loader2 size={18} aria-hidden="true" />
                  ) : (
                    <Upload size={18} aria-hidden="true" />
                  )}
                  Upload
                </button>
                <p className="item-meta">
                  PDF, DOCX, PPTX, Markdown, text, HTML, CSV, and images.
                </p>
              </div>
              {uploadResult ? <UploadSummary result={uploadResult} /> : null}
              {message ? <p className="form-message">{message}</p> : null}
            </section>

            <section className="library-panel" aria-labelledby="library-title">
              <div className="section-header">
                <h2 className="section-title" id="library-title">
                  Documents
                </h2>
                <button
                  className="icon-button"
                  type="button"
                  onClick={() => void refreshDocuments()}
                >
                  <RefreshCw size={17} aria-hidden="true" />
                  <span className="sr-only">Refresh documents</span>
                </button>
              </div>
              <div className="filter-row">
                <label>
                  <Search size={16} aria-hidden="true" />
                  <input
                    aria-label="Filter documents by title"
                    placeholder="Filter by title"
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                  />
                </label>
                <label>
                  <Filter size={16} aria-hidden="true" />
                  <select
                    aria-label="Filter documents by status"
                    value={statusFilter}
                    onChange={(event) => setStatusFilter(event.target.value)}
                  >
                    <option value="">All status</option>
                    <option value="completed">Completed</option>
                    <option value="failed">Failed</option>
                    <option value="queued">Queued</option>
                    <option value="cancelled">Cancelled</option>
                  </select>
                </label>
                <select
                  aria-label="Sort documents"
                  value={sort}
                  onChange={(event) => setSort(event.target.value)}
                >
                  <option value="created_desc">Newest</option>
                  <option value="updated_desc">Recently updated</option>
                  <option value="created_asc">Oldest</option>
                  <option value="title_asc">Title</option>
                </select>
              </div>

              {documents.items.length === 0 ? (
                <div className="empty-state">
                  <ShieldCheck size={22} aria-hidden="true" />
                  <p>No documents match the current filters.</p>
                </div>
              ) : (
                <div className="document-table" role="list">
                  {documents.items.map((document) => (
                    <button
                      className="document-row"
                      type="button"
                      key={document.id}
                      aria-pressed={document.id === selectedId}
                      onClick={() => setSelectedId(document.id)}
                    >
                      <span>
                        <strong>{document.title}</strong>
                        <small>{document.chunk_count} chunks</small>
                      </span>
                      <StatusPill tone={statusTone[document.status]}>
                        {document.status}
                      </StatusPill>
                    </button>
                  ))}
                </div>
              )}
              <div className="pagination-row">
                <button
                  type="button"
                  disabled={offset === 0}
                  onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                >
                  Previous
                </button>
                <span>
                  {documents.offset + 1}-
                  {Math.min(
                    documents.offset + documents.limit,
                    documents.total,
                  )}{" "}
                  of {documents.total}
                </span>
                <button
                  type="button"
                  disabled={offset + PAGE_SIZE >= documents.total}
                  onClick={() => setOffset(offset + PAGE_SIZE)}
                >
                  Next
                </button>
              </div>
            </section>

            <section className="detail-panel" aria-labelledby="detail-title">
              <div className="section-header">
                <h2 className="section-title" id="detail-title">
                  Details
                </h2>
                {selectedDocument ? (
                  <StatusPill tone={statusTone[selectedDocument.status]}>
                    {selectedDocument.status}
                  </StatusPill>
                ) : null}
              </div>
              {detail ? (
                <>
                  <div className="metadata-grid">
                    <Metadata
                      label="Media"
                      value={detail.media_type ?? "unknown"}
                    />
                    <Metadata
                      label="Parser"
                      value={detail.parser_name ?? "pending"}
                    />
                    <Metadata
                      label="Chunks"
                      value={String(detail.chunk_count)}
                    />
                    <Metadata
                      label="Embeddings"
                      value={String(detail.embedding_count)}
                    />
                  </div>
                  {detail.latest_job ? (
                    <JobProgress job={detail.latest_job} />
                  ) : null}
                  <div className="action-row">
                    <button
                      type="button"
                      onClick={() => void handleDocumentAction("retry")}
                    >
                      <ListRestart size={17} aria-hidden="true" />
                      Retry
                    </button>
                    <button
                      type="button"
                      onClick={() => void handleDocumentAction("reindex")}
                    >
                      <RefreshCw size={17} aria-hidden="true" />
                      Re-index
                    </button>
                    <button
                      className="danger-button"
                      type="button"
                      onClick={() => void handleDocumentAction("delete")}
                    >
                      <Trash2 size={17} aria-hidden="true" />
                      Delete
                    </button>
                  </div>
                  <div className="tags-row">
                    <label>
                      <Tags size={16} aria-hidden="true" />
                      <input
                        aria-label="Document tags"
                        value={tagsInput}
                        onChange={(event) => setTagsInput(event.target.value)}
                      />
                    </label>
                    <button type="button" onClick={() => void handleSaveTags()}>
                      Save Tags
                    </button>
                  </div>
                  <PreviewList preview={preview} />
                </>
              ) : (
                <div className="empty-state">
                  <FileText size={22} aria-hidden="true" />
                  <p>
                    Select a document to inspect extracted text and provenance.
                  </p>
                </div>
              )}
            </section>
          </div>
        )}
      </main>
    </div>
  );
}

function UploadSummary({ result }: { result: UploadResponse }) {
  return (
    <div className="upload-summary">
      {result.accepted.map((item) => (
        <p key={`${item.document_id}-${item.ingestion_job_id ?? "duplicate"}`}>
          <CheckCircle2 size={16} aria-hidden="true" />
          {item.duplicate_of_document_id
            ? `${item.title} already exists`
            : `${item.title} accepted`}
        </p>
      ))}
      {result.rejected.map((item) => (
        <p key={`${item.filename}-${item.code}`}>
          <XCircle size={16} aria-hidden="true" />
          {item.filename}: {item.detail}
        </p>
      ))}
    </div>
  );
}

function JobProgress({ job }: { job: JobDetail }) {
  return (
    <div className="job-progress">
      <div>
        <span>{job.stage}</span>
        <strong>{job.progress_percent}%</strong>
      </div>
      <progress value={job.progress_percent} max={100} />
      {job.error_detail ? (
        <p className="form-error">
          <AlertTriangle size={16} aria-hidden="true" />
          {job.error_detail}
        </p>
      ) : null}
    </div>
  );
}

function PreviewList({ preview }: { preview: PreviewResponse | null }) {
  if (!preview || preview.chunks.length === 0) {
    return (
      <div className="empty-state">
        <FileText size={22} aria-hidden="true" />
        <p>No extracted chunks are available yet.</p>
      </div>
    );
  }
  return (
    <div className="preview-list">
      {preview.chunks.map((chunk) => (
        <article key={chunk.id} className="preview-item">
          <div className="preview-meta">
            <span>Chunk {chunk.ordinal + 1}</span>
            <span>Page {String(chunk.provenance.page_number ?? "n/a")}</span>
          </div>
          <pre>{chunk.safe_text}</pre>
        </article>
      ))}
    </div>
  );
}

function Metadata({ label, value }: { label: string; value: string }) {
  return (
    <div className="metadata-item">
      <span>{label}</span>
      <strong>{value}</strong>
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
