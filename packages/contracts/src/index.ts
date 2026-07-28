export type DocumentStatus =
  | "queued"
  | "validating"
  | "scanning"
  | "extracting"
  | "normalizing"
  | "chunking"
  | "embedding"
  | "indexing"
  | "completed"
  | "failed"
  | "cancelled";

export type DocumentSummary = {
  id: string;
  title: string;
  status: DocumentStatus;
  source_kind: string;
  created_at: string;
  updated_at: string;
  tag_names: string[];
  latest_job_id: string | null;
  chunk_count: number;
};

export type DocumentListResponse = {
  items: DocumentSummary[];
  total: number;
  limit: number;
  offset: number;
};

export type JobDetail = {
  id: string;
  document_id?: string;
  document_version_id?: string | null;
  status: DocumentStatus;
  stage: string;
  progress_percent: number;
  attempts?: number;
  error_code: string | null;
  error_detail: string | null;
  stage_log: Array<Record<string, unknown>>;
  metrics: Record<string, unknown>;
  created_at?: string;
  updated_at?: string;
  started_at?: string | null;
  completed_at?: string | null;
  cancel_requested_at?: string | null;
};

export type DocumentDetail = DocumentSummary & {
  media_type: string | null;
  checksum: string | null;
  storage_size_bytes: number;
  parser_name: string | null;
  parser_version: string | null;
  embedding_count: number;
  source_metadata: Record<string, unknown>;
  extraction_metadata: Record<string, unknown>;
  latest_job: JobDetail | null;
};

export type PreviewResponse = {
  document_id: string;
  status: DocumentStatus;
  chunks: Array<{
    id: string;
    ordinal: number;
    safe_text: string;
    provenance: Record<string, unknown>;
  }>;
};

export type UploadResponse = {
  accepted: Array<{
    document_id: string;
    document_version_id: string | null;
    ingestion_job_id: string | null;
    title: string;
    status: DocumentStatus;
    checksum: string;
    media_type: string;
    duplicate_of_document_id: string | null;
  }>;
  rejected: Array<{ filename: string; code: string; detail: string }>;
};

export type JobActionResponse = {
  ingestion_job_id: string;
  status: string;
  stage: string;
};

export type TagsResponse = {
  document_id: string;
  tags: string[];
};

export type SearchMode = "lexical" | "semantic" | "hybrid";

export type SearchFilters = {
  document_ids?: string[];
  collection_ids?: string[];
  tags?: string[];
  source_types?: string[];
  created_from?: string | null;
  created_to?: string | null;
};

export type SearchRequest = {
  query: string;
  mode?: SearchMode;
  filters?: SearchFilters;
  limit?: number;
  offset?: number;
  min_score?: number;
  debug?: boolean;
};

export type SearchResult = {
  chunk_id: string;
  document_id: string;
  document_title: string;
  document_version: number;
  document_version_id: string;
  source_kind: string;
  ordinal: number;
  score: number;
  lexical_score: number | null;
  semantic_score: number | null;
  excerpt: string;
  provenance: Record<string, unknown>;
  source_preview_locator: string;
  tag_names: string[];
  allowed_citation_id?: string;
  debug?: Record<string, unknown>;
};

export type SearchResponse = {
  mode: SearchMode;
  query: string;
  items: SearchResult[];
  selected_context: SearchResult[];
  total: number;
  limit: number;
  offset: number;
  latency_ms: number;
  warnings: string[];
  request_id: string;
  trace_id: string;
  debug: Record<string, unknown> | null;
};

export type ConversationSummary = {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  archived_at: string | null;
};

export type Citation = {
  citation_id?: string;
  chunk_id: string;
  document_id: string;
  document_title: string;
  document_version: number;
  document_version_id: string;
  page?: number | null;
  slide?: number | null;
  sheet?: string | null;
  section?: unknown;
  excerpt?: string;
  quote?: string | null;
  source_preview_locator: string;
};

export type Message = {
  id: string;
  conversation_id: string;
  role: "user" | "assistant" | string;
  content: string;
  model: string | null;
  token_count: number | null;
  created_at: string;
  citations: Citation[];
};

export type ConversationDetail = ConversationSummary & {
  messages: Message[];
};

export type StreamChatPayload = {
  content: string;
  mode?: SearchMode;
  filters?: SearchFilters;
  provider?:
    | "mock"
    | "openai-compatible"
    | "openai"
    | "anthropic"
    | "gemini"
    | "vllm"
    | null;
  model?: string | null;
  min_score?: number;
  debug?: boolean;
};

export type StreamEvent = {
  event:
    | "run_started"
    | "retrieval_started"
    | "retrieval_completed"
    | "token_delta"
    | "citation"
    | "warning"
    | "usage"
    | "completed"
    | "cancelled"
    | "failed";
  data: Record<string, unknown>;
};

export type RunActionResponse = {
  run_id: string;
  state: string;
  conversation_id?: string;
  message_id?: string;
};

export type ModelCapability = {
  provider: string;
  model: string;
  supports_streaming: boolean;
  supports_structured_output: boolean;
  supports_health_check: boolean;
  configured: boolean;
  notes: string | null;
};

export type ProviderHealth = {
  provider: string;
  ok: boolean;
  configured: boolean;
  latency_ms: number | null;
  error_code: string | null;
};

export type SourceChunk = {
  chunk_id: string;
  document_id: string;
  document_title: string;
  document_version: number;
  document_version_id: string;
  text: string;
  excerpt: string;
  provenance: Record<string, unknown>;
  source_preview_locator: string;
};

export class LoomiApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "LoomiApiError";
  }
}

export function createLoomiClient(apiBase: string) {
  return {
    login(email: string, password: string) {
      return request<{ csrf_token: string }>(apiBase, "/api/v1/auth/login", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
    },
    listDocuments(params: URLSearchParams) {
      return request<DocumentListResponse>(
        apiBase,
        `/api/v1/documents?${params.toString()}`,
      );
    },
    getDocument(documentId: string) {
      return request<DocumentDetail>(
        apiBase,
        `/api/v1/documents/${documentId}`,
      );
    },
    previewDocument(documentId: string) {
      return request<PreviewResponse>(
        apiBase,
        `/api/v1/documents/${documentId}/preview`,
      );
    },
    uploadDocuments(files: File[], csrfToken: string, idempotencyKey: string) {
      const form = new FormData();
      for (const file of files) {
        form.append("files", file);
      }
      return request<UploadResponse>(apiBase, "/api/v1/documents/uploads", {
        method: "POST",
        headers: {
          "x-csrf-token": csrfToken,
          "idempotency-key": idempotencyKey,
        },
        body: form,
      });
    },
    retryDocument(
      documentId: string,
      csrfToken: string,
      idempotencyKey: string,
    ) {
      return request<JobActionResponse>(
        apiBase,
        `/api/v1/documents/${documentId}/retry`,
        {
          method: "POST",
          headers: {
            "x-csrf-token": csrfToken,
            "idempotency-key": idempotencyKey,
          },
        },
      );
    },
    reindexDocument(
      documentId: string,
      csrfToken: string,
      idempotencyKey: string,
    ) {
      return request<JobActionResponse>(
        apiBase,
        `/api/v1/documents/${documentId}/reindex`,
        {
          method: "POST",
          headers: {
            "x-csrf-token": csrfToken,
            "idempotency-key": idempotencyKey,
          },
        },
      );
    },
    deleteDocument(documentId: string, csrfToken: string) {
      return request<void>(apiBase, `/api/v1/documents/${documentId}`, {
        method: "DELETE",
        headers: { "x-csrf-token": csrfToken },
      });
    },
    updateTags(documentId: string, csrfToken: string, tags: string[]) {
      return request<TagsResponse>(
        apiBase,
        `/api/v1/documents/${documentId}/tags`,
        {
          method: "PUT",
          headers: {
            "content-type": "application/json",
            "x-csrf-token": csrfToken,
          },
          body: JSON.stringify({ tags }),
        },
      );
    },
    search(payload: SearchRequest) {
      return request<SearchResponse>(apiBase, "/api/v1/search", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(payload),
      });
    },
    listConversations() {
      return request<ConversationSummary[]>(apiBase, "/api/v1/conversations");
    },
    createConversation(csrfToken: string, title?: string) {
      return request<ConversationSummary>(apiBase, "/api/v1/conversations", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "x-csrf-token": csrfToken,
        },
        body: JSON.stringify({ title }),
      });
    },
    getConversation(conversationId: string) {
      return request<ConversationDetail>(
        apiBase,
        `/api/v1/conversations/${conversationId}`,
      );
    },
    createGenerationRun(
      conversationId: string,
      csrfToken: string,
      payload: StreamChatPayload,
    ) {
      return request<RunActionResponse>(
        apiBase,
        `/api/v1/conversations/${conversationId}/runs`,
        {
          method: "POST",
          headers: {
            "content-type": "application/json",
            "x-csrf-token": csrfToken,
          },
          body: JSON.stringify(payload),
        },
      );
    },
    streamConversationResponse(
      conversationId: string,
      csrfToken: string,
      payload: StreamChatPayload,
      onEvent: (event: StreamEvent) => void,
      signal?: AbortSignal,
    ) {
      return streamRequest(
        apiBase,
        `/api/v1/conversations/${conversationId}/responses/stream`,
        csrfToken,
        payload,
        onEvent,
        signal,
      );
    },
    retryMessageResponse(
      messageId: string,
      csrfToken: string,
      payload: StreamChatPayload,
      onEvent: (event: StreamEvent) => void,
      signal?: AbortSignal,
    ) {
      return streamRequest(
        apiBase,
        `/api/v1/messages/${messageId}/retry/stream`,
        csrfToken,
        payload,
        onEvent,
        signal,
      );
    },
    cancelRun(runId: string, csrfToken: string) {
      return request<RunActionResponse>(
        apiBase,
        `/api/v1/runs/${runId}/cancel`,
        {
          method: "POST",
          headers: { "x-csrf-token": csrfToken },
        },
      );
    },
    listModels() {
      return request<ModelCapability[]>(apiBase, "/api/v1/providers/models");
    },
    providerHealth() {
      return request<ProviderHealth[]>(apiBase, "/api/v1/providers/health");
    },
    getSourceChunk(chunkId: string) {
      return request<SourceChunk>(apiBase, `/api/v1/sources/chunks/${chunkId}`);
    },
    createFeedback(
      csrfToken: string,
      payload: {
        target_type: string;
        target_id: string;
        rating?: number | null;
        comment?: string | null;
      },
    ) {
      return request<{
        id: string;
        target_type: string;
        target_id: string;
        rating: number | null;
      }>(apiBase, "/api/v1/feedback", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "x-csrf-token": csrfToken,
        },
        body: JSON.stringify(payload),
      });
    },
  };
}

async function request<T>(
  apiBase: string,
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const response = await fetch(`${apiBase}${path}`, {
    ...init,
    credentials: "include",
  });
  if (!response.ok) {
    throw new LoomiApiError(await errorDetail(response), response.status);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

async function errorDetail(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: string };
    return payload.detail ?? response.statusText;
  } catch {
    return response.statusText || "Request failed.";
  }
}

async function streamRequest(
  apiBase: string,
  path: string,
  csrfToken: string,
  payload: StreamChatPayload,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(`${apiBase}${path}`, {
    method: "POST",
    credentials: "include",
    signal,
    headers: {
      "content-type": "application/json",
      "x-csrf-token": csrfToken,
      "idempotency-key": crypto.randomUUID(),
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new LoomiApiError(await errorDetail(response), response.status);
  }
  if (!response.body) {
    throw new LoomiApiError("Streaming response was empty.", response.status);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    buffer = drainSseBuffer(buffer, onEvent);
  }
  buffer += decoder.decode();
  drainSseBuffer(`${buffer}\n\n`, onEvent);
}

function drainSseBuffer(
  buffer: string,
  onEvent: (event: StreamEvent) => void,
): string {
  let remaining = buffer;
  let boundary = remaining.indexOf("\n\n");
  while (boundary >= 0) {
    const block = remaining.slice(0, boundary);
    remaining = remaining.slice(boundary + 2);
    const event = parseSseBlock(block);
    if (event) {
      onEvent(event);
    }
    boundary = remaining.indexOf("\n\n");
  }
  return remaining;
}

function parseSseBlock(block: string): StreamEvent | null {
  const lines = block.split("\n");
  const eventName = lines
    .find((line) => line.startsWith("event:"))
    ?.replace("event:", "")
    .trim();
  const data = lines
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.replace("data:", "").trim())
    .join("\n");
  if (!eventName || !data) {
    return null;
  }
  return {
    event: eventName as StreamEvent["event"],
    data: JSON.parse(data) as Record<string, unknown>,
  };
}
