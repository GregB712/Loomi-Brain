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

export type AgentRunLimits = {
  max_steps?: number;
  max_tool_calls?: number;
  request_timeout_seconds?: number;
  per_step_timeout_seconds?: number;
  token_budget?: number;
  cost_budget_usd?: number;
  max_retries?: number;
};

export type CreateAgentRunPayload = {
  owner_request: string;
  allowed_tools?: string[];
  limits?: AgentRunLimits;
  provider?: string | null;
  model?: string | null;
};

export type AgentEvent = {
  id: string;
  run_id: string;
  event_type: string;
  sequence_number: number;
  payload: Record<string, unknown>;
  created_at: string;
};

export type AgentToolCall = {
  id: string;
  run_id: string;
  tool_id: string;
  tool_name: string;
  risk_class: string;
  status: string;
  redacted_arguments: Record<string, unknown>;
  redacted_result: Record<string, unknown> | null;
  arguments_hash: string | null;
  idempotency_key: string | null;
  policy_decision: Record<string, unknown>;
  timeout_seconds: number | null;
  output_size_limit: number | null;
  retry_count: number;
  latency_ms: number | null;
  error_code: string | null;
  trace_id: string | null;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  completed_at: string | null;
};

export type AgentApproval = {
  id: string;
  run_id: string;
  tool_call_id: string | null;
  tool_id: string | null;
  status: string;
  policy_version: string;
  arguments_hash: string | null;
  risk_class: string | null;
  expires_at: string;
  decided_at: string | null;
  decided_by_user_id: string | null;
  used_at: string | null;
  expired_at: string | null;
  cancelled_at: string | null;
  denial_reason: string | null;
  approval_metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type AgentRunSummary = {
  id: string;
  run_kind: string;
  state: string;
  status_reason: string | null;
  owner_request: string | null;
  provider: string | null;
  model: string | null;
  allowed_tools: string[];
  limits: Record<string, unknown>;
  usage: Record<string, unknown>;
  sanitized_input: Record<string, unknown>;
  sanitized_output: Record<string, unknown> | null;
  retry_count: number;
  latency_ms: number | null;
  trace_id: string | null;
  trace_metadata: Record<string, unknown>;
  last_error: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  completed_at: string | null;
  cancel_requested_at: string | null;
};

export type AgentRunDetail = AgentRunSummary & {
  events: AgentEvent[];
  tool_calls: AgentToolCall[];
  approvals: AgentApproval[];
};

export type AgentRunListResponse = {
  items: AgentRunSummary[];
  total: number;
  limit: number;
  offset: number;
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

export type ObservabilityStatus = {
  enabled: boolean;
  exporter: string;
  local_only: boolean;
  content_capture: string;
  sample_rate: number;
  retention_days: number;
  sampling_preview: boolean;
  latest_exporter_status: string | null;
  latest_exporter_error: string | null;
  prompt_registry: Array<Record<string, unknown>>;
};

export type ObservabilitySummary = {
  range: { start: string; end: string };
  telemetry: {
    enabled: boolean;
    exporter: string;
    local_only: boolean;
    content_capture: string;
    sample_rate: number;
    retention_days: number;
    spans: number;
    error_spans: number;
    latency_p50_ms: number;
    latency_p95_ms: number;
    exporter_status: Record<string, number>;
  };
  runs: {
    total: number;
    by_state: Record<string, number>;
    success_rate: number;
    error_rate: number;
    recent: ObservabilityRun[];
  };
  model_usage: {
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
    estimated_cost_usd: number;
  };
  providers: ObservabilityProviderBreakdown[];
  retrieval: ObservabilityRetrievalSummary;
  ingestion: Record<string, unknown>;
  tools: Record<string, unknown>;
  approvals: Record<string, unknown>;
  evaluation: {
    passed: boolean;
    regressions: Array<Record<string, unknown>>;
    baseline_name: string;
  };
};

export type ObservabilityRun = {
  id: string;
  run_kind: string;
  state: string;
  status_reason: string | null;
  provider: string | null;
  model: string | null;
  usage: Record<string, unknown>;
  latency_ms: number | null;
  trace_id: string | null;
  trace_url: string | null;
  created_at: string;
  completed_at: string | null;
};

export type ObservabilityProviderBreakdown = {
  provider: string;
  model: string;
  runs: number;
  tokens: number;
  estimated_cost_usd: number;
  latency_p95_ms: number;
};

export type ObservabilityRetrievalSummary = {
  by_mode: Array<{
    mode: string;
    runs: number;
    total_candidates: number;
    selected_context: number;
    warnings: number;
    avg_candidates: number;
    avg_selected_context: number;
    latency_p95_ms: number;
  }>;
};

export type ObservabilityRetrievalResponse = {
  summary: ObservabilityRetrievalSummary;
  recent_spans: Array<Record<string, unknown>>;
};

export type ObservabilityEvaluationHistory = {
  current_synthetic_report: Record<string, unknown>;
  items: Array<Record<string, unknown>>;
};

export type ObservabilityFeedbackSummary = {
  total: number;
  by_rating: Record<string, number>;
  items: Array<Record<string, unknown>>;
};

export type MCPTransport = "stdio" | "streamable_http";

export type MCPRiskClass =
  | "read-only"
  | "local-mutation"
  | "external-mutation"
  | "credential-sensitive"
  | "destructive";

export type MCPApprovalPolicy = "never" | "risk-based" | "always";

export type MCPCapability = {
  id: string;
  server_id: string;
  tool_id: string | null;
  capability_type: "tool" | "resource" | "prompt" | string;
  name: string;
  title: string | null;
  description: string | null;
  schema: Record<string, unknown>;
  output_schema: Record<string, unknown>;
  risk_class: MCPRiskClass;
  approval_policy: MCPApprovalPolicy;
  enabled: boolean;
  schema_hash: string;
  metadata: Record<string, unknown>;
  last_seen_at: string | null;
  created_at: string;
  updated_at: string;
};

export type MCPServer = {
  id: string;
  name: string;
  description: string | null;
  transport: MCPTransport;
  enabled: boolean;
  command_template: string[];
  url: string | null;
  has_secret_ref: boolean;
  environment_allowlist: string[];
  working_directory: string | null;
  connection_timeout_seconds: number;
  tool_timeout_seconds: number;
  output_size_limit: number;
  health_status: string;
  health_detail: string | null;
  capability_cache: Record<string, unknown>;
  policy: Record<string, unknown>;
  last_connected_at: string | null;
  last_capability_refresh_at: string | null;
  last_error: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  capabilities?: MCPCapability[];
};

export type MCPServerListResponse = {
  items: MCPServer[];
  total: number;
  limit: number;
  offset: number;
  templates: Array<{ name: string; description: string }>;
};

export type CreateMCPServerPayload = {
  name: string;
  description?: string | null;
  transport: MCPTransport;
  template_name?: string | null;
  url?: string | null;
  secret_ref?: string | null;
  environment_allowlist?: string[];
  working_directory?: string | null;
  connection_timeout_seconds?: number;
  tool_timeout_seconds?: number;
  output_size_limit?: number;
  allow_private_networks?: boolean;
};

export type MCPPolicyPayload = {
  enabled: boolean;
  risk_class: MCPRiskClass;
  approval_policy: MCPApprovalPolicy;
  expected_side_effects?: string | null;
  confirm_broadening: boolean;
};

export type MCPAuditResponse = {
  items: Array<{
    id: string;
    event_type: string;
    request_id: string | null;
    trace_id: string | null;
    metadata: Record<string, unknown>;
    created_at: string;
  }>;
  limit: number;
  offset: number;
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
    createAgentRun(
      csrfToken: string,
      payload: CreateAgentRunPayload,
      idempotencyKey = crypto.randomUUID(),
    ) {
      return request<AgentRunDetail>(apiBase, "/api/v1/agent-runs", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "x-csrf-token": csrfToken,
          "idempotency-key": idempotencyKey,
        },
        body: JSON.stringify(payload),
      });
    },
    listAgentRuns(params = new URLSearchParams()) {
      const query = params.toString();
      return request<AgentRunListResponse>(
        apiBase,
        `/api/v1/agent-runs${query ? `?${query}` : ""}`,
      );
    },
    getAgentRun(runId: string) {
      return request<AgentRunDetail>(apiBase, `/api/v1/agent-runs/${runId}`);
    },
    getAgentRunEvents(runId: string) {
      return request<AgentEvent[]>(
        apiBase,
        `/api/v1/agent-runs/${runId}/events`,
      );
    },
    cancelAgentRun(runId: string, csrfToken: string) {
      return request<AgentRunDetail>(
        apiBase,
        `/api/v1/agent-runs/${runId}/cancel`,
        {
          method: "POST",
          headers: { "x-csrf-token": csrfToken },
        },
      );
    },
    retryAgentRun(runId: string, csrfToken: string) {
      return request<AgentRunDetail>(
        apiBase,
        `/api/v1/agent-runs/${runId}/retry`,
        {
          method: "POST",
          headers: { "x-csrf-token": csrfToken },
        },
      );
    },
    approveAgentToolCall(
      runId: string,
      approvalId: string,
      csrfToken: string,
      payload: { arguments?: Record<string, unknown> | null } = {},
    ) {
      return request<AgentRunDetail>(
        apiBase,
        `/api/v1/agent-runs/${runId}/approvals/${approvalId}/approve`,
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
    denyAgentToolCall(
      runId: string,
      approvalId: string,
      csrfToken: string,
      reason?: string,
    ) {
      return request<AgentRunDetail>(
        apiBase,
        `/api/v1/agent-runs/${runId}/approvals/${approvalId}/deny`,
        {
          method: "POST",
          headers: {
            "content-type": "application/json",
            "x-csrf-token": csrfToken,
          },
          body: JSON.stringify({ reason }),
        },
      );
    },
    listModels() {
      return request<ModelCapability[]>(apiBase, "/api/v1/providers/models");
    },
    providerHealth() {
      return request<ProviderHealth[]>(apiBase, "/api/v1/providers/health");
    },
    listMcpTemplates() {
      return request<{ items: Array<{ name: string; description: string }> }>(
        apiBase,
        "/api/v1/mcp/templates",
      );
    },
    listMcpServers(params = new URLSearchParams()) {
      const query = params.toString();
      return request<MCPServerListResponse>(
        apiBase,
        `/api/v1/mcp/servers${query ? `?${query}` : ""}`,
      );
    },
    createMcpServer(csrfToken: string, payload: CreateMCPServerPayload) {
      return request<MCPServer>(apiBase, "/api/v1/mcp/servers", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "x-csrf-token": csrfToken,
        },
        body: JSON.stringify(payload),
      });
    },
    getMcpServer(serverId: string) {
      return request<MCPServer>(apiBase, `/api/v1/mcp/servers/${serverId}`);
    },
    updateMcpServer(
      serverId: string,
      csrfToken: string,
      payload: Partial<CreateMCPServerPayload>,
    ) {
      return request<MCPServer>(apiBase, `/api/v1/mcp/servers/${serverId}`, {
        method: "PATCH",
        headers: {
          "content-type": "application/json",
          "x-csrf-token": csrfToken,
        },
        body: JSON.stringify(payload),
      });
    },
    setMcpServerEnabled(serverId: string, csrfToken: string, enabled: boolean) {
      return request<MCPServer>(
        apiBase,
        `/api/v1/mcp/servers/${serverId}/${enabled ? "enable" : "disable"}`,
        { method: "POST", headers: { "x-csrf-token": csrfToken } },
      );
    },
    deleteMcpServer(serverId: string, csrfToken: string, confirmName: string) {
      return request<void>(apiBase, `/api/v1/mcp/servers/${serverId}`, {
        method: "DELETE",
        headers: {
          "content-type": "application/json",
          "x-csrf-token": csrfToken,
        },
        body: JSON.stringify({ confirm_name: confirmName }),
      });
    },
    testMcpConnection(serverId: string, csrfToken: string) {
      return request<Record<string, unknown>>(
        apiBase,
        `/api/v1/mcp/servers/${serverId}/test-connection`,
        { method: "POST", headers: { "x-csrf-token": csrfToken } },
      );
    },
    refreshMcpCapabilities(serverId: string, csrfToken: string) {
      return request<MCPServer>(
        apiBase,
        `/api/v1/mcp/servers/${serverId}/refresh-capabilities`,
        { method: "POST", headers: { "x-csrf-token": csrfToken } },
      );
    },
    updateMcpCapabilityPolicy(
      capabilityId: string,
      csrfToken: string,
      payload: MCPPolicyPayload,
    ) {
      return request<MCPCapability>(
        apiBase,
        `/api/v1/mcp/capabilities/${capabilityId}/policy`,
        {
          method: "PATCH",
          headers: {
            "content-type": "application/json",
            "x-csrf-token": csrfToken,
          },
          body: JSON.stringify(payload),
        },
      );
    },
    invokeMcpCapability(
      serverId: string,
      capabilityId: string,
      csrfToken: string,
      payload: {
        arguments: Record<string, unknown>;
        owner_request?: string | null;
      },
    ) {
      return request<AgentRunDetail>(
        apiBase,
        `/api/v1/mcp/servers/${serverId}/capabilities/${capabilityId}/invoke`,
        {
          method: "POST",
          headers: {
            "content-type": "application/json",
            "x-csrf-token": csrfToken,
            "idempotency-key": crypto.randomUUID(),
          },
          body: JSON.stringify(payload),
        },
      );
    },
    mcpAudit(params = new URLSearchParams()) {
      const query = params.toString();
      return request<MCPAuditResponse>(
        apiBase,
        `/api/v1/mcp/audit${query ? `?${query}` : ""}`,
      );
    },
    observabilityStatus() {
      return request<ObservabilityStatus>(
        apiBase,
        "/api/v1/observability/status",
      );
    },
    observabilitySummary(params = new URLSearchParams()) {
      const query = params.toString();
      return request<ObservabilitySummary>(
        apiBase,
        `/api/v1/observability/summary${query ? `?${query}` : ""}`,
      );
    },
    observabilityRuns(params = new URLSearchParams()) {
      const query = params.toString();
      return request<{
        items: ObservabilityRun[];
        limit: number;
        offset: number;
      }>(apiBase, `/api/v1/observability/runs${query ? `?${query}` : ""}`);
    },
    observabilityRetrieval(params = new URLSearchParams()) {
      const query = params.toString();
      return request<ObservabilityRetrievalResponse>(
        apiBase,
        `/api/v1/observability/retrieval${query ? `?${query}` : ""}`,
      );
    },
    observabilityEvaluations(params = new URLSearchParams()) {
      const query = params.toString();
      return request<ObservabilityEvaluationHistory>(
        apiBase,
        `/api/v1/observability/evaluations${query ? `?${query}` : ""}`,
      );
    },
    observabilityFeedback(params = new URLSearchParams()) {
      const query = params.toString();
      return request<ObservabilityFeedbackSummary>(
        apiBase,
        `/api/v1/observability/feedback${query ? `?${query}` : ""}`,
      );
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
