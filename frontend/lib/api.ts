import {
  CorpusOverview,
  DocumentListResponse,
  DocumentMetadata,
  DocumentIngestionJobListResponse,
  DocumentUploadResponse,
  EvaluationResponse,
  EnterpriseSession,
  EnterpriseTenant,
  EnterpriseTenantCreate,
  EnterpriseTenantUpdate,
  AdminEventListResponse,
  AdminBatchRepairResponse,
  AdminOperationalCleanupResponse,
  AdminQdrantPruneResponse,
  AdminRuntimeResponse,
  AuditLogListResponse,
  CorpusIntegrityReport,
  EnterpriseUserCreate,
  EnterpriseUserRecord,
  EnterpriseUserUpdate,
  HealthResponse,
  LoginRequest,
  MetricsResponse,
  ObservabilityAlertsResponse,
  ObservabilitySLOResponse,
  ObservabilityTraceResponse,
  LogoutResponse,
  PasswordChangeRequest,
  PasswordResetConfirmRequest,
  PasswordResetRequestPayload,
  RecoveryRequest,
  RepairLogListResponse,
  RecoveryResponse,
  SessionRevokeRequest,
  SessionRevokeResponse,
  TenantSwitchRequest,
  QueryLogResponse,
  QueryResponse,
  QdrantCollectionListResponse,
  RepairResult,
  RetrievalProfile,
  SearchFilters,
  SearchResponse,
  UserSessionListResponse,
} from "@/types";

export class ApiError extends Error {
  status: number;
  details: unknown;

  constructor(message: string, status: number, details: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.details = details;
  }
}

const DEFAULT_API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
const SESSION_TOKEN_STORAGE_KEY = "cvg_master_rag_session_token";

let inMemorySessionToken: string | null = null;

function readStoredSessionToken(): string | null {
  if (inMemorySessionToken) return inMemorySessionToken;
  if (typeof window === "undefined") return null;
  try {
    inMemorySessionToken = window.sessionStorage.getItem(SESSION_TOKEN_STORAGE_KEY);
  } catch {
    inMemorySessionToken = null;
  }
  return inMemorySessionToken;
}

export function setApiSessionToken(token: string | null | undefined) {
  inMemorySessionToken = token || null;
  if (typeof window === "undefined") return;
  try {
    if (token) {
      window.sessionStorage.setItem(SESSION_TOKEN_STORAGE_KEY, token);
    } else {
      window.sessionStorage.removeItem(SESSION_TOKEN_STORAGE_KEY);
    }
  } catch {
    // Best effort only. The HttpOnly cookie remains the primary session path.
  }
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("Accept", "application/json");
  const sessionToken = readStoredSessionToken();
  if (sessionToken && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${sessionToken}`);
  }

  const response = await fetch(`${DEFAULT_API_BASE}${path}`, {
    ...init,
    headers,
    cache: "no-store",
    credentials: "include",
  });

  const contentType = response.headers.get("content-type") || "";
  const isJsonResponse = contentType.includes("application/json");
  const payload = isJsonResponse ? await response.json() : await response.text();

  if (!response.ok) {
    const message =
      typeof payload === "object" && payload && "detail" in payload
        ? JSON.stringify((payload as { detail: unknown }).detail)
        : typeof payload === "string"
          ? payload
          : response.statusText;
    throw new ApiError(message || "Request failed", response.status, payload);
  }

  if (!isJsonResponse) {
    throw new ApiError("Unexpected non-JSON response", response.status, payload);
  }

  return payload as T;
}

export const api = {
  baseUrl: DEFAULT_API_BASE,

  health: (workspaceId?: string, options: { light?: boolean } = {}) => {
    const search = new URLSearchParams();
    if (workspaceId) search.set("workspace_id", workspaceId);
    if (options.light) search.set("light", "true");
    const query = search.toString();
    return requestJson<HealthResponse>(query ? `/health?${query}` : "/health");
  },

  session: {
    current: () => requestJson<EnterpriseSession>("/session"),
    me: () => requestJson<EnterpriseSession>("/auth/me"),
    login: (params: LoginRequest) =>
      requestJson<EnterpriseSession>("/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(params),
      }),
    logout: () =>
      requestJson<LogoutResponse>("/auth/logout", {
        method: "POST",
      }),
    switchTenant: (tenantId: string) =>
      requestJson<EnterpriseSession>("/auth/switch-tenant", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tenant_id: tenantId } satisfies TenantSwitchRequest),
      }),
    recovery: (params: RecoveryRequest) =>
      requestJson<RecoveryResponse>("/auth/recovery", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(params),
      }),
    requestPasswordReset: (params: PasswordResetRequestPayload) =>
      requestJson<RecoveryResponse>("/auth/request-password-reset", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(params),
      }),
    confirmPasswordReset: (params: PasswordResetConfirmRequest) =>
      requestJson<RecoveryResponse>("/auth/confirm-password-reset", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(params),
      }),
    changePassword: (params: PasswordChangeRequest) =>
      requestJson<RecoveryResponse>("/auth/change-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(params),
      }),
    sessions: () => requestJson<UserSessionListResponse>("/auth/sessions"),
    revokeSessions: (params: SessionRevokeRequest) =>
      requestJson<SessionRevokeResponse>("/auth/sessions/revoke", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(params),
      }),
    tenants: () => requestJson<EnterpriseTenant[]>("/tenants"),
  },

  admin: {
    tenants: {
      list: () => requestJson<EnterpriseTenant[]>("/admin/tenants"),
      create: (params: EnterpriseTenantCreate) =>
        requestJson<EnterpriseTenant>("/admin/tenants", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(params),
        }),
      update: (tenantId: string, params: EnterpriseTenantUpdate) =>
        requestJson<EnterpriseTenant>(`/admin/tenants/${encodeURIComponent(tenantId)}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(params),
        }),
      remove: (tenantId: string) =>
        requestJson<{ status: string; tenant_id: string }>(`/admin/tenants/${encodeURIComponent(tenantId)}`, {
          method: "DELETE",
        }),
    },
    users: {
      list: () => requestJson<EnterpriseUserRecord[]>("/admin/users"),
      create: (params: EnterpriseUserCreate) =>
        requestJson<EnterpriseUserRecord>("/admin/users", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(params),
        }),
      update: (userId: string, params: EnterpriseUserUpdate) =>
        requestJson<EnterpriseUserRecord>(`/admin/users/${encodeURIComponent(userId)}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(params),
        }),
      remove: (userId: string) =>
        requestJson<{ status: string; user_id: string }>(`/admin/users/${encodeURIComponent(userId)}`, {
          method: "DELETE",
        }),
      resetPassword: (userId: string, reason?: string) =>
        requestJson<{ status: string; reset_id: string; reset_token: string; expires_at: string }>(
          `/admin/users/${encodeURIComponent(userId)}/reset-password`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ reason }),
          },
        ),
    },
    events: {
      list: (params: { limit?: number; offset?: number; action?: string; tenant_id?: string; workspace_id?: string } = {}) => {
        const query = new URLSearchParams({
          limit: String(params.limit ?? 20),
          offset: String(params.offset ?? 0),
        });
        if (params.action) query.set("action", params.action);
        if (params.tenant_id) query.set("tenant_id", params.tenant_id);
        if (params.workspace_id) query.set("workspace_id", params.workspace_id);
        return requestJson<AdminEventListResponse>(`/admin/events?${query.toString()}`);
      },
    },
    runtime: () => requestJson<AdminRuntimeResponse>("/admin/runtime"),
    pruneIndex: (workspaceId: string) => {
      const query = new URLSearchParams({ workspace_id: workspaceId });
      return requestJson<AdminQdrantPruneResponse>(`/admin/runtime/prune-index?${query.toString()}`, {
        method: "POST",
      });
    },
    cleanupOperational: (workspaceId: string) => {
      const query = new URLSearchParams({ workspace_id: workspaceId });
      return requestJson<AdminOperationalCleanupResponse>(`/admin/runtime/cleanup-operational?${query.toString()}`, {
        method: "POST",
      });
    },
    alerts: (workspaceId?: string, days = 1) => {
      const query = new URLSearchParams({ days: String(days) });
      if (workspaceId) query.set("workspace_id", workspaceId);
      return requestJson<ObservabilityAlertsResponse>(`/admin/alerts?${query.toString()}`);
    },
    slo: (workspaceId?: string, days = 7) => {
      const query = new URLSearchParams({ days: String(days) });
      if (workspaceId) query.set("workspace_id", workspaceId);
      return requestJson<ObservabilitySLOResponse>(`/admin/slo?${query.toString()}`);
    },
    traces: (workspaceId?: string, limit = 20) => {
      const query = new URLSearchParams({ limit: String(limit) });
      if (workspaceId) query.set("workspace_id", workspaceId);
      return requestJson<ObservabilityTraceResponse>(`/admin/traces?${query.toString()}`);
    },
    audits: (workspaceId?: string, params: { days?: number; limit?: number; offset?: number } = {}) => {
      const query = new URLSearchParams({
        days: String(params.days ?? 30),
        limit: String(params.limit ?? 10),
        offset: String(params.offset ?? 0),
      });
      if (workspaceId) query.set("workspace_id", workspaceId);
      return requestJson<AuditLogListResponse>(`/admin/audits?${query.toString()}`);
    },
    repairs: (workspaceId?: string, params: { days?: number; limit?: number; offset?: number } = {}) => {
      const query = new URLSearchParams({
        days: String(params.days ?? 30),
        limit: String(params.limit ?? 10),
        offset: String(params.offset ?? 0),
      });
      if (workspaceId) query.set("workspace_id", workspaceId);
      return requestJson<RepairLogListResponse>(`/admin/repairs?${query.toString()}`);
    },
    runEvaluation: (
      workspaceId: string,
      params: { runJudge?: boolean; reranking?: boolean; rerankingMethod?: string; queryExpansion?: boolean } = {},
    ) => {
      const query = new URLSearchParams({
        workspace_id: workspaceId,
        run_judge: params.runJudge ? "true" : "false",
        reranking: params.reranking ? "true" : "false",
        query_expansion: params.queryExpansion ? "true" : "false",
      });
      if (params.rerankingMethod) query.set("reranking_method", params.rerankingMethod);
      return requestJson<EvaluationResponse>(`/admin/evaluation/run?${query.toString()}`, {
        method: "POST",
      });
    },
    runCorpusAudit: (workspaceId: string, checkEmbeddings = false) => {
      const query = new URLSearchParams({
        workspace_id: workspaceId,
        check_embeddings: checkEmbeddings ? "true" : "false",
      });
      return requestJson<CorpusIntegrityReport>(`/admin/corpus/audit?${query.toString()}`, {
        method: "POST",
      });
    },
    repairDocument: (workspaceId: string, documentId: string) => {
      const query = new URLSearchParams({
        workspace_id: workspaceId,
      });
      return requestJson<RepairResult>(`/admin/corpus/repair/${encodeURIComponent(documentId)}?${query.toString()}`, {
        method: "POST",
      });
    },
    repairBatch: (workspaceId: string, params: { limit?: number; checkEmbeddings?: boolean } = {}) => {
      const query = new URLSearchParams({
        workspace_id: workspaceId,
        limit: String(params.limit ?? 20),
        check_embeddings: params.checkEmbeddings ? "true" : "false",
      });
      return requestJson<AdminBatchRepairResponse>(`/admin/corpus/repair-batch?${query.toString()}`, {
        method: "POST",
      });
    },
  },

  documents: {
    list: (
      workspaceId = "default",
      params: {
        limit?: number;
        offset?: number;
        source_type?: string;
        status?: string;
        query?: string;
      } = {},
    ) => {
      const search = new URLSearchParams({
        workspace_id: workspaceId,
        limit: String(params.limit ?? 50),
        offset: String(params.offset ?? 0),
      });
      if (params.source_type) search.set("source_type", params.source_type);
      if (params.status) search.set("status", params.status);
      if (params.query) search.set("query", params.query);
      return requestJson<DocumentListResponse>(`/documents?${search.toString()}`);
    },
    get: (documentId: string, workspaceId = "default") =>
      requestJson<DocumentMetadata>(
        `/documents/${encodeURIComponent(documentId)}?workspace_id=${encodeURIComponent(workspaceId)}`,
      ),
    listIngestionJobs: (workspaceId = "default", limit = 10) => {
      const search = new URLSearchParams({
        workspace_id: workspaceId,
        limit: String(limit),
      });
      return requestJson<DocumentIngestionJobListResponse>(`/documents/ingestion-jobs?${search.toString()}`);
    },
    listQdrantCollections: (workspaceId = "default") => {
      const search = new URLSearchParams({ workspace_id: workspaceId });
      return requestJson<QdrantCollectionListResponse>(`/documents/qdrant-collections?${search.toString()}`);
    },
    upload: async (file: File, workspaceId = "default", qdrantCollection?: string) => {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("workspace_id", workspaceId);
      if (qdrantCollection) formData.append("qdrant_collection", qdrantCollection);
      return requestJson<DocumentUploadResponse>("/documents/upload", {
        method: "POST",
        body: formData,
      });
    },
  },

  search: (params: {
    query: string;
    workspace_id?: string;
    top_k?: number;
    threshold?: number;
    filters?: SearchFilters | null;
    include_raw_scores?: boolean;
    retrieval_profile?: RetrievalProfile | null;
  }) =>
    requestJson<SearchResponse>("/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(params),
    }),

  query: (params: {
    query: string;
    workspace_id?: string;
    top_k?: number;
    threshold?: number;
    stream?: boolean;
    model?: string | null;
    retrieval_profile?: RetrievalProfile | null;
  }) =>
    requestJson<QueryResponse>("/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(params),
    }),

  metrics: (days = 7, workspaceId?: string) => {
    const search = new URLSearchParams({ days: String(days) });
    if (workspaceId) search.set("workspace_id", workspaceId);
    return requestJson<MetricsResponse>(`/metrics?${search.toString()}`);
  },

  observability: {
    alerts: (days = 1, workspaceId?: string) => {
      const search = new URLSearchParams({ days: String(days) });
      if (workspaceId) search.set("workspace_id", workspaceId);
      return requestJson<ObservabilityAlertsResponse>(`/observability/alerts?${search.toString()}`);
    },
    slo: (workspaceId = "default") => {
      const search = new URLSearchParams({ workspace_id: workspaceId });
      return requestJson<ObservabilitySLOResponse>(`/observability/slo?${search.toString()}`);
    },
    traces: (workspaceId = "default", limit = 20) => {
      const search = new URLSearchParams({ workspace_id: workspaceId, limit: String(limit) });
      return requestJson<ObservabilityTraceResponse>(`/observability/traces?${search.toString()}`);
    },
    audits: (
      workspaceId = "default",
      params: { days?: number; limit?: number; offset?: number } = {},
    ) => {
      const search = new URLSearchParams({
        workspace_id: workspaceId,
        days: String(params.days ?? 30),
        limit: String(params.limit ?? 10),
        offset: String(params.offset ?? 0),
      });
      return requestJson<AuditLogListResponse>(`/observability/audits?${search.toString()}`);
    },
    repairs: (
      workspaceId = "default",
      params: { days?: number; limit?: number; offset?: number } = {},
    ) => {
      const search = new URLSearchParams({
        workspace_id: workspaceId,
        days: String(params.days ?? 30),
        limit: String(params.limit ?? 10),
        offset: String(params.offset ?? 0),
      });
      return requestJson<RepairLogListResponse>(`/observability/repairs?${search.toString()}`);
    },
  },

  evaluation: {
    dataset: (workspaceId = "default") =>
      requestJson<{ dataset_id: string; version: string; questions: unknown[] }>(
        `/evaluation/dataset?workspace_id=${encodeURIComponent(workspaceId)}`,
      ),
    run: (workspaceId = "default", runJudge = false) =>
      requestJson<EvaluationResponse>(
        `/evaluation/run?workspace_id=${encodeURIComponent(workspaceId)}&run_judge=${runJudge ? "true" : "false"}`,
        { method: "POST" },
      ),
  },

  corpus: () =>
    requestJson<HealthResponse>(`/health`).then((payload) => payload.corpus as CorpusOverview),

  queries: {
    list: (
      workspaceId = "default",
      params: {
        limit?: number;
        offset?: number;
        low_confidence?: boolean;
        needs_review?: boolean;
        grounded?: boolean;
        min_citation_coverage?: number;
      } = {},
    ) => {
      const query = new URLSearchParams({
        workspace_id: workspaceId,
        limit: String(params.limit ?? 50),
        offset: String(params.offset ?? 0),
      });
      if (params.low_confidence !== undefined) query.set("low_confidence", String(params.low_confidence));
      if (params.needs_review !== undefined) query.set("needs_review", String(params.needs_review));
      if (params.grounded !== undefined) query.set("grounded", String(params.grounded));
      if (params.min_citation_coverage !== undefined) {
        query.set("min_citation_coverage", String(params.min_citation_coverage));
      }
      return requestJson<QueryLogResponse>(`/queries/logs?${query.toString()}`);
    },
  },
};
