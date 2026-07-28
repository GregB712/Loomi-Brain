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
