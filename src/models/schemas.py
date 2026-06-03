from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime
from uuid import uuid4

EnterpriseRole = Literal["super_admin", "admin_rag", "auditor", "operator", "viewer", "admin"]


# ─── Document ───────────────────────────────────────────────


class DocumentUploadResponse(BaseModel):
    document_id: str
    status: Literal["parsed", "failed", "partial", "queued", "processing"]
    catalog_scope: Literal["canonical", "operational"] = "canonical"
    source_type: str
    filename: str
    page_count: Optional[int] = None
    char_count: int
    chunk_count: int
    created_at: str
    chunking_strategy: str = "recursive"
    qdrant_collection: Optional[str] = None
    ingestion_id: Optional[str] = None
    message: Optional[str] = None


class DocumentIngestionJobStatus(BaseModel):
    ingestion_id: str
    document_id: str
    final_document_id: Optional[str] = None
    workspace_id: str
    filename: str
    source_type: str
    chunking_strategy: Optional[str] = None
    qdrant_collection: Optional[str] = None
    file_size_bytes: Optional[int] = None
    large_job: bool = False
    resource_profile: Optional[str] = None
    resource_isolation_mode: Optional[str] = None
    resource_limits: dict = Field(default_factory=dict)
    status: Literal["pending", "processing", "committed", "failed", "aborted"]
    page_count: Optional[int] = None
    pages_processed: int = 0
    chunks_written: int = 0
    qdrant_points_written: int = 0
    rss_peak_mb: Optional[float] = None
    last_heartbeat_at: Optional[str] = None
    last_batch_at: Optional[str] = None
    pages_per_minute: Optional[float] = None
    chunks_per_minute: Optional[float] = None
    seconds_since_last_batch: Optional[int] = None
    operational_status: Optional[Literal["pending", "running", "warning", "stalled", "failed", "completed"]] = None
    operational_alerts: list[dict] = Field(default_factory=list)
    created_at: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None


class DocumentIngestionJobListResponse(BaseModel):
    items: list[DocumentIngestionJobStatus] = Field(default_factory=list)
    total: int
    limit: int
    workspace_id: str


class DocumentMetadata(BaseModel):
    document_id: str
    workspace_id: str
    catalog_scope: Literal["canonical", "operational"] = "canonical"
    source_type: str
    filename: str
    page_count: Optional[int] = None
    char_count: int
    chunk_count: int
    status: Literal["parsed", "failed", "partial"]
    created_at: str
    chunking_strategy: str = "recursive"
    tags: list[str] = Field(default_factory=list)
    embeddings_model: Optional[str] = None
    qdrant_collection: Optional[str] = None
    indexed_at: Optional[str] = None


class DocumentListItem(DocumentMetadata):
    file_path: Optional[str] = None


class DocumentListResponse(BaseModel):
    items: list[DocumentListItem] = Field(default_factory=list)
    total: int
    limit: int
    offset: int
    workspace_id: str


class QdrantCollectionListResponse(BaseModel):
    active_collection: str
    collections: list[str] = Field(default_factory=list)


# ─── Enterprise Session ─────────────────────────────────────


class EnterpriseTenant(BaseModel):
    tenant_id: str
    name: str
    workspace_id: str
    plan: Literal["starter", "business", "enterprise"] = "enterprise"
    status: Literal["active", "suspended"] = "active"
    document_count: int = 0
    operational_retention_mode: Literal["keep_latest", "keep_all"] = "keep_latest"
    operational_retention_hours: int = 24


class EnterpriseUser(BaseModel):
    user_id: str
    name: str
    email: str
    role: EnterpriseRole
    permissions: list[str] = Field(default_factory=list)


class EnterpriseSession(BaseModel):
    authenticated: bool = True
    session_state: Literal["active", "expired", "anonymous"] = "active"
    expires_at: Optional[str] = None
    session_token: Optional[str] = None
    user: EnterpriseUser
    active_tenant: EnterpriseTenant
    available_tenants: list[EnterpriseTenant] = Field(default_factory=list)
    message: Optional[str] = None


class LoginRequest(BaseModel):
    email: str
    password: str
    tenant_id: str = "default"


class RecoveryRequest(BaseModel):
    email: str
    tenant_id: Optional[str] = None
    reason: Optional[str] = None


class RecoveryResponse(BaseModel):
    status: Literal["queued"] = "queued"
    message: str


class LogoutResponse(BaseModel):
    status: Literal["signed_out"] = "signed_out"


class TenantSwitchRequest(BaseModel):
    tenant_id: str


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str


class PasswordResetRequestPayload(BaseModel):
    email: str
    tenant_id: Optional[str] = None


class PasswordResetConfirmRequest(BaseModel):
    token: str
    new_password: str


class PasswordResetAdminRequest(BaseModel):
    reason: Optional[str] = None
    expires_in_minutes: int = 30


class UserSessionRecord(BaseModel):
    session_token: str
    user_id: str
    tenant_id: str
    role: EnterpriseRole
    permissions: list[str] = Field(default_factory=list)
    created_at: str
    last_seen_at: Optional[str] = None
    expires_at: str
    revoked_at: Optional[str] = None
    revoked_reason: Optional[str] = None
    current: bool = False
    ip: Optional[str] = None
    user_agent: Optional[str] = None


class UserSessionListResponse(BaseModel):
    items: list[UserSessionRecord] = Field(default_factory=list)
    total: int


class SessionRevokeRequest(BaseModel):
    session_token: Optional[str] = None
    user_id: Optional[str] = None
    revoke_all: bool = False
    reason: Optional[str] = None


class SessionRevokeResponse(BaseModel):
    revoked: int
    message: str


class AdminEvent(BaseModel):
    timestamp: str
    type: Literal["admin_event"] = "admin_event"
    actor_user_id: str
    actor_email: str
    actor_role: str
    action: str
    target_type: str
    target_id: str
    tenant_id: Optional[str] = None
    metadata: dict = Field(default_factory=dict)


class AdminEventListResponse(BaseModel):
    items: list[AdminEvent] = Field(default_factory=list)
    total: int
    limit: int
    offset: int


class AdminTenantRuntimeSummary(BaseModel):
    tenant_id: str
    name: str
    workspace_id: str
    plan: Literal["starter", "business", "enterprise"] = "enterprise"
    status: Literal["active", "suspended"] = "active"
    document_count: int = 0
    chunk_count: int = 0
    parsed_documents: int = 0
    partial_documents: int = 0
    operational_documents: int = 0
    operational_chunks: int = 0
    operational_retention_mode: Literal["keep_latest", "keep_all"] = "keep_latest"
    operational_retention_hours: int = 24
    operational_cleanup_eligible_documents: int = 0
    operational_cleanup_eligible_chunks: int = 0
    operational_cleanup_oldest_created_at: Optional[str] = None
    qdrant_status: Literal["ok", "error"] = "error"
    qdrant_points: Optional[int] = None
    qdrant_canonical_points: int = 0
    qdrant_noncanonical_points: int = 0
    qdrant_noncanonical_documents: int = 0
    alerts_active: int = 0
    critical_alerts: int = 0
    audit_events_30d: int = 0
    repair_events_30d: int = 0
    readiness_score: int = 0
    readiness_status: Literal["ready", "stable", "at_risk", "critical"] = "critical"
    readiness_reasons: list[str] = Field(default_factory=list)
    groundedness_rate: float = 0.0
    no_context_rate: float = 0.0
    evaluation_hit_rate_top5: float = 0.0
    p95_latency_ms: float = 0.0
    latest_query_at: Optional[str] = None
    latest_ingestion_at: Optional[str] = None
    latest_evaluation_at: Optional[str] = None


class AdminRuntimeResponse(BaseModel):
    items: list[AdminTenantRuntimeSummary] = Field(default_factory=list)
    total: int
    qdrant_collection: str
    generated_at: str


class AdminQdrantPruneResponse(BaseModel):
    workspace_id: str
    deleted_points: int = 0
    deleted_documents: int = 0
    deleted_document_ids: list[str] = Field(default_factory=list)
    canonical_points_remaining: int = 0
    total_points_remaining: int = 0
    generated_at: str


class AdminOperationalCleanupResponse(BaseModel):
    workspace_id: str
    retention_mode: Literal["keep_latest", "keep_all"] = "keep_latest"
    retention_hours: int = 24
    deleted_documents: int = 0
    deleted_chunks: int = 0
    deleted_document_ids: list[str] = Field(default_factory=list)
    remaining_operational_documents: int = 0
    remaining_operational_chunks: int = 0
    generated_at: str


class ObservabilityAlert(BaseModel):
    name: str
    severity: Literal["critical", "high", "medium"]
    status: Literal["ok", "firing"]
    message: str
    window: str
    value: Optional[float | int | str] = None
    threshold: Optional[float | int | str] = None


class ObservabilityAlertsResponse(BaseModel):
    items: list[ObservabilityAlert] = Field(default_factory=list)
    total_active: int = 0
    workspace_id: Optional[str] = None
    period_days: int = 1
    generated_at: str


class ObservabilitySLOItem(BaseModel):
    name: str
    description: str
    category: Literal["availability", "latency", "quality", "reliability"]
    unit: str
    window: str
    current_value: float
    target_value: float
    alert_threshold: Optional[float] = None
    comparator: Literal["at_most", "at_least"]
    healthy: bool
    status: Literal["ok", "breach"]
    message: str


class ObservabilitySLOResponse(BaseModel):
    items: list[ObservabilitySLOItem] = Field(default_factory=list)
    total_breaches: int = 0
    workspace_id: Optional[str] = None
    generated_at: str


class TraceSpanEvent(BaseModel):
    name: str
    attributes: dict = Field(default_factory=dict)


class TraceSpanRecord(BaseModel):
    name: str
    trace_id: str
    span_id: str
    parent_id: Optional[str] = None
    kind: str
    status: str
    workspace_id: Optional[str] = None
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    duration_ms: Optional[float] = None
    attributes: dict = Field(default_factory=dict)
    events: list[TraceSpanEvent] = Field(default_factory=list)


class ObservabilityTraceResponse(BaseModel):
    items: list[TraceSpanRecord] = Field(default_factory=list)
    total: int = 0
    workspace_id: Optional[str] = None
    generated_at: str


class AuditLogEvent(BaseModel):
    timestamp: str
    type: Literal["audit"] = "audit"
    request_id: Optional[str] = None
    workspace_id: str
    total_documents: int = 0
    total_with_issues: int = 0
    total_ok: int = 0
    by_issue_type: dict[str, int] = Field(default_factory=dict)
    recommendations: list[str] = Field(default_factory=list)


class AuditLogListResponse(BaseModel):
    items: list[AuditLogEvent] = Field(default_factory=list)
    total: int
    limit: int
    offset: int
    workspace_id: Optional[str] = None


class RepairLogEvent(BaseModel):
    timestamp: str
    type: Literal["repair"] = "repair"
    request_id: Optional[str] = None
    document_id: str
    workspace_id: str
    success: bool
    chunks_reindexed: int = 0
    embeddings_valid: bool = False
    qdrant_restored: bool = False
    message: str = ""


class RepairLogListResponse(BaseModel):
    items: list[RepairLogEvent] = Field(default_factory=list)
    total: int
    limit: int
    offset: int
    workspace_id: Optional[str] = None


class EnterpriseTenantCreate(BaseModel):
    tenant_id: str
    name: str
    workspace_id: str
    plan: Literal["starter", "business", "enterprise"] = "starter"
    status: Literal["active", "suspended"] = "active"
    operational_retention_mode: Literal["keep_latest", "keep_all"] = "keep_latest"
    operational_retention_hours: int = 24


class EnterpriseTenantUpdate(BaseModel):
    name: Optional[str] = None
    workspace_id: Optional[str] = None
    plan: Optional[Literal["starter", "business", "enterprise"]] = None
    status: Optional[Literal["active", "suspended"]] = None
    operational_retention_mode: Optional[Literal["keep_latest", "keep_all"]] = None
    operational_retention_hours: Optional[int] = None


class EnterpriseUserRecord(BaseModel):
    user_id: str
    name: str
    email: str
    role: EnterpriseRole
    tenant_id: str
    status: Literal["active", "invited", "disabled"] = "active"
    permissions: list[str] = Field(default_factory=list)
    must_change_password: bool = False


class EnterpriseUserCreate(BaseModel):
    user_id: str
    name: str
    email: str
    password: str
    role: EnterpriseRole = "viewer"
    tenant_id: str = "default"
    status: Literal["active", "invited", "disabled"] = "invited"


class EnterpriseUserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None
    role: Optional[EnterpriseRole] = None
    tenant_id: Optional[str] = None
    status: Optional[Literal["active", "invited", "disabled"]] = None
    approve_sensitive_change: Optional[bool] = None
    approval_ticket: Optional[str] = None
    must_change_password: Optional[bool] = None


class NormalizedDocument(BaseModel):
    """Internal JSON representation of a parsed document."""

    document_id: str
    source_type: str
    filename: str
    workspace_id: str
    created_at: str
    pages: list[dict] = Field(default_factory=list)
    sections: list[dict] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    raw_json_path: str = ""


# ─── Chunk ───────────────────────────────────────────────────


class Chunk(BaseModel):
    chunk_id: str
    document_id: str
    workspace_id: str
    chunk_index: int
    text: str
    start_char: int
    end_char: int
    page_hint: Optional[int] = None
    strategy: str = "recursive"
    chunk_size_chars: int = 0
    created_at: str


# ─── Retrieval ───────────────────────────────────────────────


RetrievalProfile = Literal[
    "hybrid",
    "hyde_hybrid",
    "semantic_hybrid",
    "semantic_hyde_hybrid",
    "clinical_v2",
]


class SearchRequest(BaseModel):
    query: str
    workspace_id: str = "default"
    top_k: int = 5
    threshold: float = 0.25
    retrieval_mode: str = "híbrida"
    filters: Optional[dict] = None
    include_raw_scores: bool = False
    # Optional: None = use global RERANKING_ENABLED config, True = force on, False = force off
    reranking: Optional[bool] = None
    # Optional: override global RERANKING_METHOD ("bm25f", "neural", "none")
    reranking_method: Optional[str] = None
    # Query expansion mode: "off" = never, "always" = always when enabled, "adaptive" = use heuristic
    # None = use global QUERY_EXPANSION_ENABLED config
    query_expansion_mode: Optional[Literal["off", "always", "adaptive"]] = None
    retrieval_profile: Optional[RetrievalProfile] = None


class SearchResultItem(BaseModel):
    chunk_id: str
    document_id: str
    text: str
    score: float
    page_hint: Optional[int] = None
    source: str
    document_filename: Optional[str] = None
    workspace_id: Optional[str] = None
    source_type: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    query_variant: Optional[dict] = None
    query_variants: list[dict] = Field(default_factory=list)
    clinical_categories: list[str] = Field(default_factory=list)
    primary_clinical_category: Optional[str] = None
    clinical_category_matches: dict = Field(default_factory=dict)


class SearchResponse(BaseModel):
    query: str
    workspace_id: str
    results: list[SearchResultItem]
    total_candidates: int
    low_confidence: bool
    retrieval_time_ms: int
    method: str = "híbrida"
    scores_breakdown: Optional[dict] = None
    reranking_applied: bool = False
    reranking_method: Optional[str] = None
    query_expansion_applied: bool = False
    query_expansion_method: Optional[str] = None
    query_expansion_fallback: bool = False
    query_expansion_requested: bool = False
    query_expansion_mode: Optional[Literal["off", "always", "adaptive"]] = None
    query_expansion_decision_reason: Optional[str] = None
    retrieval_profile: Optional[RetrievalProfile] = None


# ─── Query / Answer ─────────────────────────────────────────


class QueryRequest(BaseModel):
    query: str
    workspace_id: str = "default"
    top_k: int = 5
    threshold: float = 0.25
    stream: bool = False
    model: Optional[str] = None
    reranking: Optional[bool] = None  # None = use global config, True/False override
    reranking_method: Optional[str] = None  # None = use global RERANKING_METHOD, or "bm25f"/"neural"/"none"
    # "off" = never, "always" = always when enabled, "adaptive" = use heuristic
    # None = use global config
    # Deprecated: query_expansion=True/False still works as before (maps to always/off)
    query_expansion_mode: Optional[Literal["off", "always", "adaptive"]] = None
    query_expansion: Optional[bool] = None  # Deprecated: use query_expansion_mode instead
    retrieval_profile: Optional[RetrievalProfile] = None


class GroundingReport(BaseModel):
    grounded: bool
    citation_coverage: float = 0.0
    uncited_claims: list[str] = Field(default_factory=list)
    needs_review: bool = False
    reason: Optional[str] = None


class Citation(BaseModel):
    chunk_id: str
    document_id: Optional[str] = None
    document_filename: Optional[str] = None
    page: Optional[int] = None
    text: str
    score: float
    section: Optional[str] = None
    sections: list[str] = Field(default_factory=list)


ClinicalSectionKey = Literal[
    "resumo",
    "historico_resenha",
    "sinais_sintomas",
    "exames_complementares",
    "tratamento_clinico",
    "tratamento_cirurgico",
    "proximos_passos",
    "referencias",
]


class ClinicalAnswerSections(BaseModel):
    resumo: Optional[str] = None
    historico_resenha: Optional[str] = None
    sinais_sintomas: Optional[str] = None
    exames_complementares: Optional[str] = None
    tratamento_clinico: Optional[str] = None
    tratamento_cirurgico: Optional[str] = None
    proximos_passos: Optional[str] = None
    referencias: Optional[str] = None


class ClinicalResponseGuardrails(BaseModel):
    scope_preserved: bool
    translation_context_preserved: bool
    unsupported_claims: list[str] = Field(default_factory=list)
    bibliographic_grounding: bool


class ClinicalBibliographyReference(BaseModel):
    chunk_id: str
    document_id: Optional[str] = None
    document_filename: Optional[str] = None
    page: Optional[int] = None
    sections: list[ClinicalSectionKey] = Field(default_factory=list)


class ClinicalEvidenceItem(BaseModel):
    chunk_id: str
    text: str
    score: float
    section: ClinicalSectionKey
    document_id: Optional[str] = None
    document_filename: Optional[str] = None
    page: Optional[int] = None
    query_variant: Optional[dict] = None
    query_variants: list[dict] = Field(default_factory=list)
    clinical_categories: list[ClinicalSectionKey] = Field(default_factory=list)
    bibliographic_reference: ClinicalBibliographyReference
    relevance_reason: Optional[str] = None


class ClinicalEvidenceSection(BaseModel):
    section: ClinicalSectionKey
    status: Literal["found", "missing"]
    items: list[ClinicalEvidenceItem] = Field(default_factory=list)
    bibliography: list[ClinicalBibliographyReference] = Field(default_factory=list)
    placeholder: Optional[str] = None


class ClinicalEvidencePack(BaseModel):
    query: str
    workspace_id: str = "default"
    source_method: str
    section_order: list[ClinicalSectionKey] = Field(default_factory=list)
    sections: dict[str, ClinicalEvidenceSection] = Field(default_factory=dict)
    bibliography: list[ClinicalBibliographyReference] = Field(default_factory=list)
    missing_sections: list[ClinicalSectionKey] = Field(default_factory=list)
    total_items: int = 0


class ClinicalGeneratedAnswer(BaseModel):
    answer_markdown: str
    sections: ClinicalAnswerSections
    missing_sections: list[ClinicalSectionKey] = Field(default_factory=list)
    bibliography: list[ClinicalBibliographyReference] = Field(default_factory=list)
    bibliography_footer: Optional[str] = None
    evidence_chunk_ids: list[str] = Field(default_factory=list)
    section_citation_map: dict[str, list[str]] = Field(default_factory=dict)
    section_grounding: dict[str, bool] = Field(default_factory=dict)
    completeness_status: Literal["sufficient", "partial"] = "sufficient"
    completeness_note: str = "A evidencia recuperada cobre as secoes criticas disponiveis."
    guardrails: ClinicalResponseGuardrails = Field(
        default_factory=lambda: ClinicalResponseGuardrails(
            scope_preserved=True,
            translation_context_preserved=True,
            unsupported_claims=[],
            bibliographic_grounding=True,
        )
    )
    generated_by: Literal["deterministic_evidence_pack", "llm_evidence_pack"] = "deterministic_evidence_pack"


class QueryResponse(BaseModel):
    answer: str
    answer_markdown: Optional[str] = None
    chunks_used: list[str]
    citations: list[Citation] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"]
    grounded: bool
    grounding: Optional[GroundingReport] = None  # Grounding verification details
    citation_coverage: float = 0.0  # 0.0-1.0
    low_confidence: bool
    retrieval: dict
    latency_ms: int
    query_expansion_applied: bool = False
    query_expansion_method: Optional[str] = None
    query_expansion_fallback: bool = False
    query_expansion_requested: bool = False
    query_expansion_mode: Optional[Literal["off", "always", "adaptive"]] = None
    query_expansion_decision_reason: Optional[str] = None
    retrieval_profile: Optional[RetrievalProfile] = None
    sections: Optional[ClinicalAnswerSections] = None
    bibliography: list[ClinicalBibliographyReference] = Field(default_factory=list)
    bibliography_footer: Optional[str] = None
    missing_sections: list[ClinicalSectionKey] = Field(default_factory=list)
    guardrails: Optional[ClinicalResponseGuardrails] = None
    completeness_status: Optional[Literal["sufficient", "partial"]] = None
    completeness_note: Optional[str] = None
    section_citation_map: dict[str, list[str]] = Field(default_factory=dict)
    section_grounding: dict[str, bool] = Field(default_factory=dict)


class ExternalChatRequest(BaseModel):
    question: str = Field(min_length=3, max_length=4000)
    workspace_id: str = "default"
    top_k: int = Field(default=8, ge=1, le=20)
    threshold: float = Field(default=0.25, ge=0.0, le=1.0)


class ExternalChatResponse(BaseModel):
    answer: str
    confidence: Literal["high", "medium", "low"]
    grounded: bool
    low_confidence: bool
    citation_coverage: float
    citations: list[Citation] = Field(default_factory=list)
    bibliography: list[ClinicalBibliographyReference] = Field(default_factory=list)
    chunks_used: list[str] = Field(default_factory=list)
    retrieval_profile: RetrievalProfile = "clinical_v2"
    latency_ms: int
    completeness_status: Optional[Literal["sufficient", "partial"]] = None
    missing_sections: list[ClinicalSectionKey] = Field(default_factory=list)


# ─── Evaluation ──────────────────────────────────────────────


class EvaluationQuestion(BaseModel):
    id: int
    pergunta: str
    document_id: str
    document_filename: Optional[str] = None
    trecho_esperado: str
    resposta_esperada: str
    dificuldade: Literal["easy", "medium", "hard"] = "medium"
    categoria: Literal["fato", "procedimento", "política", "detalhes"] = "procedimento"
    workspace_id: str = "default"
    query_expansion: Optional[bool] = None  # override global expansion for this question


class Dataset(BaseModel):
    dataset_id: str
    version: str = "1.0"
    questions: list[EvaluationQuestion]


class ClinicalEvaluationQuestion(BaseModel):
    id: str
    query: str
    species: str
    clinical_problem: str
    organ_system: Optional[str] = None
    intent: Literal["diagnostico", "protocolo", "tratamento", "exames", "resumo"] = "protocolo"
    expected_sections: list[ClinicalSectionKey] = Field(default_factory=list)
    required_evidence: list[str] = Field(default_factory=list)
    required_terms_pt: list[str] = Field(default_factory=list)
    required_terms_en: list[str] = Field(default_factory=list)
    allowed_missing_sections: list[ClinicalSectionKey] = Field(default_factory=list)
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    workspace_id: str = "default"


class ClinicalEvaluationDataset(BaseModel):
    dataset_id: str
    version: str = "1.0"
    target_language: str = "pt-BR"
    description: Optional[str] = None
    questions: list[ClinicalEvaluationQuestion]


class ClinicalQueryVariant(BaseModel):
    variant_type: Literal["original", "technical_pt", "technical_en", "synonyms", "section_focus"]
    query: str
    purpose: Optional[str] = None
    origin: Optional[
        Literal[
            "user_original",
            "planner_terms_pt",
            "planner_terms_en",
            "planner_synonyms",
            "planner_section_focus",
            "llm",
        ]
    ] = None
    context_preserved: bool = True
    blocked: bool = False
    blocked_reason: Optional[str] = None


class ClinicalQueryPlan(BaseModel):
    original_query: str
    detected_language: str = "pt-BR"
    species: Optional[str] = None
    clinical_problem: Optional[str] = None
    organ_system: Optional[str] = None
    intent: Literal["diagnostico", "protocolo", "tratamento", "exames", "resumo", "unknown"] = "unknown"
    canonical_terms_pt: list[str] = Field(default_factory=list)
    canonical_terms_en: list[str] = Field(default_factory=list)
    synonyms: list[str] = Field(default_factory=list)
    required_terms: list[str] = Field(default_factory=list)
    low_signal_terms: list[str] = Field(default_factory=list)
    desired_sections: list[ClinicalSectionKey] = Field(default_factory=list)
    query_variants: list[ClinicalQueryVariant] = Field(default_factory=list)
    scope_warning: Optional[str] = None
    planner_notes: Optional[str] = None
    answers_user: bool = False
    generated_by: Literal["llm", "deterministic_fallback"] = "deterministic_fallback"


class ClinicalExpectedFixture(BaseModel):
    question_id: str
    required_sections: list[ClinicalSectionKey] = Field(default_factory=list)
    allowed_missing_sections: list[ClinicalSectionKey] = Field(default_factory=list)
    min_bibliography_references: int = 1
    required_reference_fields: list[str] = Field(default_factory=list)
    required_footer_heading: str = "## Referencias bibliograficas"
    required_guardrails: list[str] = Field(default_factory=list)
    forbidden_response_patterns: list[str] = Field(default_factory=list)


class ClinicalExpectedFixtureSet(BaseModel):
    fixture_id: str
    version: str = "1.0"
    dataset_id: str
    fixtures: list[ClinicalExpectedFixture]


class EvaluationResult(BaseModel):
    question_id: str
    pergunta: str
    hit_top_1: bool
    hit_top_3: bool
    hit_top_5: bool
    retrieved_documents: list[str]
    correct_document_id: Optional[str] = None
    best_score: Optional[float] = None
    best_score_rank: Optional[int] = None
    judge_score: Optional[float] = None
    grounded: bool = False
    citation_coverage: float = 0.0
    low_confidence: bool = False
    retrieval_low_confidence: bool = False
    judge_groundedness: Optional[str] = None
    needs_review: bool = False
    reranking_applied: bool = False
    reranking_method: Optional[str] = None


class EvaluationResponse(BaseModel):
    evaluation_id: str
    workspace_id: str
    total_questions: int
    hit_rate_top_1: float
    hit_rate_top_3: float
    hit_rate_top_5: float
    avg_latency_ms: float
    avg_score: float = 0.0
    low_confidence_rate: float
    retrieval_low_confidence_rate: float = 0.0
    groundedness_rate: float
    observed_groundedness_rate: float = 0.0
    judge_score: Optional[float] = None
    judged_questions: int = 0
    judge_groundedness_rate: Optional[float] = None
    judge_needs_review_rate: Optional[float] = None
    flagged_for_review_count: int
    duration_seconds: float
    by_difficulty: dict = Field(default_factory=dict)
    by_category: dict = Field(default_factory=dict)
    question_results: list[EvaluationResult] = Field(default_factory=list)
    reranking_applied: bool = False
    reranking_method: Optional[str] = None


class VariantResult(BaseModel):
    """Metrics for a single A/B variant."""
    variant_name: str
    reranking_applied: bool
    reranking_method: Optional[str] = None
    query_expansion_applied: bool = False
    query_expansion_method: Optional[str] = None
    total_questions: int
    hit_rate_top_1: float
    hit_rate_top_3: float
    hit_rate_top_5: float
    avg_latency_ms: float
    avg_score: float = 0.0
    low_confidence_rate: float
    judge_score: Optional[float] = None
    duration_seconds: float


class ABEvaluationResponse(BaseModel):
    """Structured A/B comparison result."""
    evaluation_id: str
    workspace_id: str
    baseline: VariantResult
    variant: VariantResult
    delta_hit_at_1: float = 0.0
    delta_hit_at_3: float = 0.0
    delta_hit_at_5: float = 0.0
    delta_avg_latency_ms: float = 0.0
    delta_avg_score: float = 0.0
    delta_low_confidence_rate: float = 0.0
    winner: Optional[Literal["baseline", "variant", "tie"]] = None


class ChunkingVariantResult(BaseModel):
    """Metrics for a single chunking strategy in a chunking A/B comparison."""
    strategy: Literal["recursive", "semantic"]
    chunk_count: int
    hit_rate_top_1: float
    hit_rate_top_3: float
    hit_rate_top_5: float
    avg_latency_ms: float
    avg_score: float = 0.0
    low_confidence_rate: float
    judge_score: Optional[float] = None
    duration_seconds: float


class ChunkingABResponse(BaseModel):
    """Structured A/B comparison result for chunking strategies."""
    evaluation_id: str
    workspace_id: str
    document_id: str
    baseline: ChunkingVariantResult
    variant: ChunkingVariantResult
    delta_hit_at_1: float = 0.0
    delta_hit_at_3: float = 0.0
    delta_hit_at_5: float = 0.0
    delta_avg_latency_ms: float = 0.0
    delta_avg_score: float = 0.0
    delta_low_confidence_rate: float = 0.0
    winner: Optional[Literal["baseline", "variant", "tie"]] = None
    corpus_restored: bool = True
    # Embedding restore quality:
    #   "original" — backup had valid embeddings and they were used as-is
    #   "regenerated" — backup had no/invalid embeddings; were regenerated from text
    #   "degraded_zero_fallback" — backup had no/invalid embeddings AND regeneration API
    #                              also failed; Qdrant indexed with zero vectors
    embedding_status: Literal["original", "regenerated", "degraded_zero_fallback"] = "original"


class QueryLogItem(BaseModel):
    timestamp: str
    type: str = "query"
    request_id: Optional[str] = None
    workspace_id: str
    query: str
    answer: str
    confidence: Literal["high", "medium", "low"]
    grounded: bool
    low_confidence: bool
    chunks_used_count: int
    chunk_ids: list[str] = Field(default_factory=list)
    retrieval_time_ms: int
    total_latency_ms: int
    results_count: int
    citation_coverage: float = 0.0
    top_result_score: Optional[float] = None
    threshold: Optional[float] = None
    hit: Optional[bool] = None
    grounding_reason: Optional[str] = None
    uncited_claims_count: int = 0
    needs_review: Optional[bool] = None
    reranking_applied: bool = False
    reranking_method: Optional[str] = None
    candidate_count: Optional[int] = None
    query_expansion_applied: bool = False
    query_expansion_method: Optional[str] = None
    query_expansion_fallback: bool = False
    query_expansion_requested: bool = False
    query_expansion_mode: Optional[Literal["off", "always", "adaptive"]] = None
    query_expansion_decision_reason: Optional[str] = None
    expansion_latency_ms: int = 0


class QueryExpansionVariantResult(BaseModel):
    """Metrics for a single query expansion variant."""
    variant_name: str
    query_expansion_applied: bool
    query_expansion_method: Optional[str] = None
    total_questions: int
    hit_rate_top_1: float
    hit_rate_top_3: float
    hit_rate_top_5: float
    avg_latency_ms: float
    avg_score: float = 0.0
    low_confidence_rate: float
    judge_score: Optional[float] = None
    duration_seconds: float


class QueryExpansionABResponse(BaseModel):
    """Structured A/B comparison for query expansion (baseline vs variant with expansion)."""
    evaluation_id: str
    workspace_id: str
    baseline: QueryExpansionVariantResult
    variant: QueryExpansionVariantResult
    delta_hit_at_1: float = 0.0
    delta_hit_at_3: float = 0.0
    delta_hit_at_5: float = 0.0
    delta_avg_latency_ms: float = 0.0
    delta_avg_score: float = 0.0
    delta_low_confidence_rate: float = 0.0
    winner: Optional[Literal["baseline", "variant", "tie"]] = None


class QueryLogResponse(BaseModel):
    items: list[QueryLogItem] = Field(default_factory=list)
    total: int
    limit: int
    offset: int
    workspace_id: str
