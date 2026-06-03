export type HealthResponse = {
  status: "healthy" | "degraded";
  version: string;
  mode?: "light" | "full";
  workspace_id?: string | null;
  qdrant?: {
    status: "ok" | "error";
    collection?: string;
    points: number | null;
    workspace_points?: number | null;
  };
  corpus?: {
    workspace_id: string;
    documents: number;
    chunks: number;
    parsed_documents: number;
    partial_documents: number;
    operational_documents: number;
    operational_chunks: number;
  };
  telemetry?: {
    period_days: number;
    workspace_id?: string | null;
    window_start: string;
    queries: { count: number; low_confidence: number; needs_review: number; latest_timestamp?: string | null };
    ingestion: { count: number; errors: number; latest_timestamp?: string | null };
    evaluation: { count: number; latest_timestamp?: string | null };
  };
  timestamp: string;
};

export type DocumentMetadata = {
  document_id: string;
  workspace_id: string;
  catalog_scope: "canonical" | "operational";
  source_type: string;
  filename: string;
  page_count: number | null;
  char_count: number;
  chunk_count: number;
  status: "parsed" | "failed" | "partial";
  created_at: string;
  chunking_strategy: string;
  tags: string[];
  embeddings_model: string | null;
  qdrant_collection?: string | null;
  indexed_at: string | null;
};

export type DocumentListItem = DocumentMetadata & {
  file_path?: string | null;
};

export type DocumentUploadResponse = {
  document_id: string;
  status: "parsed" | "failed" | "partial" | "queued" | "processing";
  catalog_scope: "canonical" | "operational";
  source_type: string;
  filename: string;
  page_count: number | null;
  char_count: number;
  chunk_count: number;
  created_at: string;
  chunking_strategy?: string;
  qdrant_collection?: string | null;
  ingestion_id?: string | null;
  message?: string | null;
};

export type DocumentIngestionJobStatus = {
  ingestion_id: string;
  document_id: string;
  final_document_id?: string | null;
  workspace_id: string;
  filename: string;
  source_type: string;
  chunking_strategy?: string | null;
  qdrant_collection?: string | null;
  file_size_bytes?: number | null;
  large_job: boolean;
  resource_profile?: string | null;
  resource_isolation_mode?: string | null;
  resource_limits: Record<string, unknown>;
  status: "pending" | "processing" | "committed" | "failed" | "aborted";
  page_count?: number | null;
  pages_processed: number;
  chunks_written: number;
  qdrant_points_written: number;
  rss_peak_mb?: number | null;
  last_heartbeat_at?: string | null;
  last_batch_at?: string | null;
  pages_per_minute?: number | null;
  chunks_per_minute?: number | null;
  seconds_since_last_batch?: number | null;
  operational_status?: "pending" | "running" | "warning" | "stalled" | "failed" | "completed" | null;
  operational_alerts?: Array<{
    code?: string;
    severity?: "warning" | "critical" | string;
    message?: string;
  }>;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
  error_code?: string | null;
  error_message?: string | null;
};

export type DocumentIngestionJobListResponse = {
  items: DocumentIngestionJobStatus[];
  total: number;
  limit: number;
  workspace_id: string;
};

export type QdrantCollectionListResponse = {
  active_collection: string;
  collections: string[];
};

export type SearchFilters = {
  document_id?: string;
  source_type?: string;
  tags?: string[];
  page_hint_min?: number;
  page_hint_max?: number;
};

export type RetrievalProfile =
  | "hybrid"
  | "hyde_hybrid"
  | "semantic_hybrid"
  | "semantic_hyde_hybrid"
  | "clinical_v2";

export type SearchResultItem = {
  chunk_id: string;
  document_id: string;
  text: string;
  score: number;
  page_hint: number | null;
  source: string;
  document_filename?: string | null;
  workspace_id?: string | null;
  source_type?: string | null;
  tags?: string[];
};

export type SearchResponse = {
  query: string;
  workspace_id: string;
  results: SearchResultItem[];
  total_candidates: number;
  low_confidence: boolean;
  retrieval_time_ms: number;
  method: string;
  scores_breakdown?: Record<string, number> | null;
  retrieval_profile?: RetrievalProfile | null;
  query_expansion_applied?: boolean;
  query_expansion_method?: string | null;
  query_expansion_fallback?: boolean;
  query_expansion_requested?: boolean;
  query_expansion_mode?: "off" | "always" | "adaptive" | null;
  query_expansion_decision_reason?: string | null;
};

export type GroundingReport = {
  grounded: boolean;
  citation_coverage: number;
  uncited_claims: string[];
  needs_review: boolean;
  reason?: string | null;
};

export type Citation = {
  chunk_id: string;
  document_id?: string | null;
  document_filename?: string | null;
  page?: number | null;
  text: string;
  score: number;
  section?: string | null;
  sections?: string[];
};

export type ClinicalSectionKey =
  | "resumo"
  | "historico_resenha"
  | "sinais_sintomas"
  | "exames_complementares"
  | "tratamento_clinico"
  | "tratamento_cirurgico"
  | "proximos_passos"
  | "referencias";

export type ClinicalAnswerSections = Partial<Record<ClinicalSectionKey, string | null>>;

export type ClinicalBibliographyReference = {
  chunk_id: string;
  document_id?: string | null;
  document_filename?: string | null;
  page?: number | null;
  sections: ClinicalSectionKey[];
};

export type ClinicalResponseGuardrails = {
  scope_preserved: boolean;
  translation_context_preserved: boolean;
  unsupported_claims: string[];
  bibliographic_grounding: boolean;
};

export type QueryResponse = {
  answer: string;
  answer_markdown?: string | null;
  chunks_used: string[];
  citations: Citation[];
  confidence: "high" | "medium" | "low";
  grounded: boolean;
  grounding?: GroundingReport | null;
  citation_coverage: number;
  low_confidence: boolean;
  retrieval: SearchResponse;
  latency_ms: number;
  retrieval_profile?: RetrievalProfile | null;
  query_expansion_applied?: boolean;
  query_expansion_method?: string | null;
  query_expansion_fallback?: boolean;
  query_expansion_requested?: boolean;
  query_expansion_mode?: "off" | "always" | "adaptive" | null;
  query_expansion_decision_reason?: string | null;
  sections?: ClinicalAnswerSections | null;
  bibliography?: ClinicalBibliographyReference[];
  bibliography_footer?: string | null;
  missing_sections?: ClinicalSectionKey[];
  guardrails?: ClinicalResponseGuardrails | null;
  completeness_status?: "sufficient" | "partial" | null;
  completeness_note?: string | null;
  section_citation_map?: Record<string, string[]>;
  section_grounding?: Record<string, boolean>;
};

export type EvaluationQuestion = {
  id: number;
  pergunta: string;
  document_id: string;
  document_filename?: string | null;
  trecho_esperado: string;
  resposta_esperada: string;
  dificuldade: "easy" | "medium" | "hard";
  categoria: "fato" | "procedimento" | "política" | "detalhes";
  workspace_id: string;
};

export type EvaluationResult = {
  question_id: string;
  pergunta: string;
  hit_top_1: boolean;
  hit_top_3: boolean;
  hit_top_5: boolean;
  retrieved_documents: string[];
  correct_document_id?: string | null;
  best_score?: number | null;
  best_score_rank?: number | null;
  judge_score?: number | null;
  grounded: boolean;
  citation_coverage: number;
  low_confidence: boolean;
  retrieval_low_confidence: boolean;
  judge_groundedness?: string | null;
  needs_review: boolean;
};

export type EvaluationResponse = {
  evaluation_id: string;
  workspace_id: string;
  total_questions: number;
  hit_rate_top_1: number;
  hit_rate_top_3: number;
  hit_rate_top_5: number;
  avg_latency_ms: number;
  avg_score: number;
  low_confidence_rate: number;
  retrieval_low_confidence_rate: number;
  groundedness_rate: number;
  observed_groundedness_rate: number;
  judge_score?: number | null;
  judged_questions: number;
  judge_groundedness_rate?: number | null;
  judge_needs_review_rate?: number | null;
  flagged_for_review_count: number;
  duration_seconds: number;
  by_difficulty: Record<string, { count: number; hit_rate_top5: number }>;
  by_category: Record<string, { count: number; hit_rate_top5: number }>;
  question_results: EvaluationResult[];
};

export type CorpusOverview = {
  workspace_id: string;
  documents: number;
  chunks: number;
  parsed_documents: number;
  partial_documents: number;
};

export type QueryLogItem = {
  timestamp: string;
  type: "query";
  request_id?: string | null;
  workspace_id: string;
  query: string;
  answer: string;
  confidence: "high" | "medium" | "low";
  grounded: boolean;
  low_confidence: boolean;
  chunks_used_count: number;
  chunk_ids: string[];
  retrieval_time_ms: number;
  total_latency_ms: number;
  results_count: number;
  citation_coverage: number;
  top_result_score?: number | null;
  threshold?: number | null;
  hit?: boolean | null;
  grounding_reason?: string | null;
  uncited_claims_count?: number;
  needs_review?: boolean | null;
};

export type DocumentListResponse = {
  workspace_id: string;
  items: DocumentListItem[];
  total: number;
  limit: number;
  offset: number;
};

export type EnterpriseRole = "super_admin" | "admin_rag" | "auditor" | "operator" | "viewer" | "admin";

export type EnterpriseTenant = {
  tenant_id: string;
  name: string;
  workspace_id: string;
  plan: "starter" | "business" | "enterprise";
  status: "active" | "suspended";
  operational_retention_mode: "keep_latest" | "keep_all";
  operational_retention_hours: number;
  document_count: number;
};

export type EnterpriseTenantCreate = {
  tenant_id: string;
  name: string;
  workspace_id: string;
  plan: "starter" | "business" | "enterprise";
  status: "active" | "suspended";
  operational_retention_mode: "keep_latest" | "keep_all";
  operational_retention_hours: number;
};

export type EnterpriseTenantUpdate = Partial<Pick<EnterpriseTenantCreate, "name" | "workspace_id" | "plan" | "status" | "operational_retention_mode" | "operational_retention_hours">>;

export type EnterpriseUser = {
  user_id: string;
  name: string;
  email: string;
  role: EnterpriseRole;
  permissions: string[];
};

export type EnterpriseUserRecord = {
  user_id: string;
  name: string;
  email: string;
  role: EnterpriseRole;
  tenant_id: string;
  status: "active" | "invited" | "disabled";
  permissions?: string[];
  must_change_password?: boolean;
};

export type EnterpriseUserCreate = {
  user_id: string;
  name: string;
  email: string;
  role: EnterpriseRole;
  tenant_id: string;
  status: "active" | "invited" | "disabled";
};

export type EnterpriseUserUpdate = Partial<Pick<EnterpriseUserCreate, "name" | "email" | "role" | "tenant_id" | "status">> & {
  approve_sensitive_change?: boolean;
  approval_ticket?: string;
  must_change_password?: boolean;
};

export type PasswordChangeRequest = {
  current_password: string;
  new_password: string;
};

export type PasswordResetRequestPayload = {
  email: string;
  tenant_id?: string | null;
};

export type PasswordResetConfirmRequest = {
  token: string;
  new_password: string;
};

export type UserSessionRecord = {
  session_token: string;
  user_id: string;
  tenant_id: string;
  role: EnterpriseRole;
  permissions: string[];
  created_at: string;
  last_seen_at?: string | null;
  expires_at: string;
  revoked_at?: string | null;
  revoked_reason?: string | null;
  current: boolean;
  ip?: string | null;
  user_agent?: string | null;
};

export type UserSessionListResponse = {
  items: UserSessionRecord[];
  total: number;
};

export type SessionRevokeRequest = {
  session_token?: string;
  user_id?: string;
  revoke_all?: boolean;
  reason?: string;
};

export type SessionRevokeResponse = {
  revoked: number;
  message: string;
};

export type AdminEvent = {
  timestamp: string;
  type: "admin_event";
  actor_user_id: string;
  actor_email: string;
  actor_role: string;
  action: string;
  target_type: string;
  target_id: string;
  tenant_id?: string | null;
  metadata: Record<string, unknown>;
};

export type AdminEventListResponse = {
  items: AdminEvent[];
  total: number;
  limit: number;
  offset: number;
};

export type AdminTenantRuntimeSummary = {
  tenant_id: string;
  name: string;
  workspace_id: string;
  plan: "starter" | "business" | "enterprise";
  status: "active" | "suspended";
  document_count: number;
  chunk_count: number;
  parsed_documents: number;
  partial_documents: number;
  operational_documents: number;
  operational_chunks: number;
  operational_retention_mode: "keep_latest" | "keep_all";
  operational_retention_hours: number;
  operational_cleanup_eligible_documents: number;
  operational_cleanup_eligible_chunks: number;
  operational_cleanup_oldest_created_at?: string | null;
  qdrant_status: "ok" | "error";
  qdrant_points?: number | null;
  qdrant_canonical_points: number;
  qdrant_noncanonical_points: number;
  qdrant_noncanonical_documents: number;
  alerts_active: number;
  critical_alerts: number;
  audit_events_30d: number;
  repair_events_30d: number;
  readiness_score: number;
  readiness_status: "ready" | "stable" | "at_risk" | "critical";
  readiness_reasons: string[];
  groundedness_rate: number;
  no_context_rate: number;
  evaluation_hit_rate_top5: number;
  p95_latency_ms: number;
  latest_query_at?: string | null;
  latest_ingestion_at?: string | null;
  latest_evaluation_at?: string | null;
};

export type AdminRuntimeResponse = {
  items: AdminTenantRuntimeSummary[];
  total: number;
  qdrant_collection: string;
  generated_at: string;
};

export type AdminQdrantPruneResponse = {
  workspace_id: string;
  deleted_points: number;
  deleted_documents: number;
  deleted_document_ids: string[];
  canonical_points_remaining: number;
  total_points_remaining: number;
  generated_at: string;
};

export type AdminOperationalCleanupResponse = {
  workspace_id: string;
  retention_mode: "keep_latest" | "keep_all";
  retention_hours: number;
  deleted_documents: number;
  deleted_chunks: number;
  deleted_document_ids: string[];
  remaining_operational_documents: number;
  remaining_operational_chunks: number;
  generated_at: string;
};

export type ObservabilityAlert = {
  name: string;
  severity: "critical" | "high" | "medium";
  status: "ok" | "firing";
  message: string;
  window: string;
  value?: number | string | null;
  threshold?: number | string | null;
};

export type ObservabilityAlertsResponse = {
  items: ObservabilityAlert[];
  total_active: number;
  workspace_id?: string | null;
  period_days: number;
  generated_at: string;
};

export type ObservabilitySLOItem = {
  name: string;
  description: string;
  category: "availability" | "latency" | "quality" | "reliability";
  unit: string;
  window: string;
  current_value: number;
  target_value: number;
  alert_threshold?: number | null;
  comparator: "at_most" | "at_least";
  healthy: boolean;
  status: "ok" | "breach";
  message: string;
};

export type ObservabilitySLOResponse = {
  items: ObservabilitySLOItem[];
  total_breaches: number;
  workspace_id?: string | null;
  generated_at: string;
};

export type TraceSpanEvent = {
  name: string;
  attributes: Record<string, unknown>;
};

export type TraceSpanRecord = {
  name: string;
  trace_id: string;
  span_id: string;
  parent_id?: string | null;
  kind: string;
  status: string;
  workspace_id?: string | null;
  started_at?: string | null;
  ended_at?: string | null;
  duration_ms?: number | null;
  attributes: Record<string, unknown>;
  events: TraceSpanEvent[];
};

export type ObservabilityTraceResponse = {
  items: TraceSpanRecord[];
  total: number;
  workspace_id?: string | null;
  generated_at: string;
};

export type AuditLogEvent = {
  timestamp: string;
  type: "audit";
  request_id?: string | null;
  workspace_id: string;
  total_documents: number;
  total_with_issues: number;
  total_ok: number;
  by_issue_type: Record<string, number>;
  recommendations: string[];
};

export type AuditLogListResponse = {
  items: AuditLogEvent[];
  total: number;
  limit: number;
  offset: number;
  workspace_id?: string | null;
};

export type RepairLogEvent = {
  timestamp: string;
  type: "repair";
  request_id?: string | null;
  document_id: string;
  workspace_id: string;
  success: boolean;
  chunks_reindexed: number;
  embeddings_valid: boolean;
  qdrant_restored: boolean;
  message: string;
};

export type RepairLogListResponse = {
  items: RepairLogEvent[];
  total: number;
  limit: number;
  offset: number;
  workspace_id?: string | null;
};

export type IntegrityIssue = {
  issue_type: string;
  severity: string;
  detail: string;
};

export type DocumentIntegrityResult = {
  document_id: string;
  chunk_count_registry: number;
  chunk_count_qdrant?: number | null;
  chunking_strategy: string;
  status: string;
  issues: IntegrityIssue[];
  repair_action?: string | null;
};

export type CorpusIntegrityReport = {
  workspace_id: string;
  total_documents: number;
  total_with_issues: number;
  total_ok: number;
  by_issue_type: Record<string, number>;
  documents: DocumentIntegrityResult[];
  recommendations: string[];
  generated_at: string;
};

export type RepairResult = {
  document_id: string;
  workspace_id: string;
  success: boolean;
  chunks_reindexed: number;
  embeddings_valid: boolean;
  qdrant_restored: boolean;
  message: string;
};

export type BatchRepairItem = {
  document_id: string;
  success: boolean;
  chunks_reindexed: number;
  embeddings_valid: boolean;
  qdrant_restored: boolean;
  message: string;
};

export type AdminBatchRepairResponse = {
  workspace_id: string;
  attempted: number;
  repaired: number;
  failed: number;
  items: BatchRepairItem[];
};

export type EnterpriseSession = {
  authenticated: boolean;
  session_state: "active" | "expired" | "anonymous";
  expires_at?: string | null;
  session_token?: string | null;
  user: EnterpriseUser;
  active_tenant: EnterpriseTenant;
  available_tenants: EnterpriseTenant[];
  message?: string | null;
};

export type LoginRequest = {
  email: string;
  password: string;
  tenant_id: string;
};

export type RecoveryRequest = {
  email: string;
  tenant_id?: string | null;
  reason?: string | null;
};

export type RecoveryResponse = {
  status: "queued";
  message: string;
};

export type LogoutResponse = {
  status: "signed_out";
};

export type TenantSwitchRequest = {
  tenant_id: string;
};

export type QueryLogResponse = {
  workspace_id: string;
  items: QueryLogItem[];
  total: number;
  limit: number;
  offset: number;
};

export type MetricsResponse = {
  workspace_id?: string | null;
  retrieval: {
    total_queries: number;
    hit_rate_top1: number;
    hit_rate_top3: number;
    hit_rate_top5: number;
    low_confidence_rate: number;
    avg_latency_ms: number;
    avg_retrieval_latency_ms: number;
    p50_latency_ms: number;
    p95_latency_ms: number;
    p99_latency_ms: number;
    avg_score_top1: number;
    avg_score: number;
    groundedness_rate: number;
    below_threshold_rate: number;
    queries_with_hit_data: number;
  };
  ingestion: {
    total_documents_processed: number;
    by_type: Record<string, number>;
    parse_success_rate: number;
    avg_chunks_per_document: number;
    avg_processing_time_ms: number;
    errors: number;
  };
  answer: {
    total_queries: number;
    groundedness_rate: number;
    no_context_rate: number;
    avg_chunks_used: number;
    citation_coverage_avg: number;
  };
  evaluation: {
    total_runs: number;
    latest_evaluation_id?: string | null;
    total_questions: number;
    hit_rate_top1: number;
    hit_rate_top3: number;
    hit_rate_top5: number;
    avg_score: number;
    avg_latency_ms: number;
    groundedness_rate: number;
    low_confidence_rate: number;
  };
  period_days: number;
  generated_at: string;
};
