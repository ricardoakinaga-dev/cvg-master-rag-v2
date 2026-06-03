"""
RAG API — FastAPI application for Phase 0 Foundation RAG
"""
import json
import hmac
import os
import sys
from pathlib import Path
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Query, Depends, Header, Request, Response, Cookie
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from models.schemas import (
    DocumentUploadResponse, DocumentMetadata, DocumentIngestionJobListResponse,
    DocumentListResponse, QdrantCollectionListResponse, QueryLogResponse,
    SearchRequest, SearchResponse,
    QueryRequest, QueryResponse,
    ExternalChatRequest, ExternalChatResponse,
    EvaluationQuestion, Dataset,
    EnterpriseSession, EnterpriseTenant, EnterpriseTenantCreate, EnterpriseTenantUpdate,
    EnterpriseUserCreate, EnterpriseUserRecord, EnterpriseUserUpdate,
    AdminEventListResponse,
    AuditLogListResponse,
    ObservabilityAlertsResponse,
    ObservabilitySLOResponse,
    ObservabilityTraceResponse,
    RepairLogListResponse,
    LoginRequest, LogoutResponse, RecoveryRequest, RecoveryResponse,
    PasswordChangeRequest, PasswordResetRequestPayload, PasswordResetConfirmRequest, PasswordResetAdminRequest,
    UserSessionListResponse, SessionRevokeRequest, SessionRevokeResponse,
    TenantSwitchRequest,
)
from services.admin_service import (
    create_tenant,
    create_user,
    delete_tenant,
    delete_user,
    get_user,
    list_tenants as list_admin_tenants,
    list_admin_events,
    log_admin_event,
    list_users,
    user_has_permission,
    reset_admin_state,
    update_tenant,
    update_user,
)
from services.enterprise_service import (
    admin_issue_password_reset,
    SESSION_COOKIE_NAME,
    bootstrap_session,
    confirm_password_reset,
    extract_session_token,
    get_session as get_enterprise_session,
    list_sessions_for_user,
    login as login_enterprise_user,
    list_tenants,
    logout as logout_enterprise_session,
    queue_recovery,
    request_password_reset,
    revoke_session as revoke_enterprise_session,
    revoke_user_sessions,
    switch_tenant as switch_enterprise_tenant,
)
from core.config import (
    SUPPORTED_EXTENSIONS,
    DOCUMENTS_DIR,
    DATA_DIR,
    CORS_ALLOWED_ORIGINS,
    CORS_ALLOW_CREDENTIALS,
    SESSION_COOKIE_SECURE,
    SESSION_COOKIE_SAMESITE,
)
from services.telemetry_service import get_telemetry
from services.request_context import clear_request_id, set_request_id
from services.vector_service import get_client
from services.document_registry import get_corpus_overview, get_workspace_inventory, list_document_items
from services.api_security import (
    enterprise_session_from_authorization,
    coerce_session,
    require_authenticated_session,
    require_min_role,
    audit_access_denied,
    session_has_permission,
    require_permission,
    require_admin,
    require_operator,
    require_workspace_access,
    resolve_workspace_scope,
)
from telemetry.slo import SLI_DEFINITIONS, get_all_slos, get_slo_status
from telemetry.tracing import SpanKind, SpanStatus, list_recent_spans, record_exception, start_span, traced_span
from api.admin_runtime_routes import router as admin_runtime_router
from api.health_routes import router as health_router
from api.observability_routes import router as observability_router, _build_slo_snapshot


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize shared resources at startup."""
    if os.getenv("RAG_SKIP_QDRANT_BOOTSTRAP", "").lower() not in {"1", "true", "yes", "on"}:
        try:
            from services.vector_service import ensure_collection
            ensure_collection()
        except Exception as e:
            print(f"WARNING: Could not initialize Qdrant collection: {e}")
    yield


app = FastAPI(
    title="RAG Database Builder — Fase 0",
    description="Foundation RAG com busca híbrida (dense + sparse + RRF)",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(admin_runtime_router)
app.include_router(health_router)
app.include_router(observability_router)

allowed_cors_origins = CORS_ALLOWED_ORIGINS

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_cors_origins,
    allow_credentials=CORS_ALLOW_CREDENTIALS,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID", "X-API-Key"],
)


ROLE_ORDER = {"viewer": 0, "operator": 1, "auditor": 2, "admin_rag": 3, "super_admin": 4, "admin": 4}
SESSION_COOKIE_MAX_AGE = 60 * 60 * 8
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(50 * 1024 * 1024)))
UPLOAD_STREAM_CHUNK_BYTES = 1024 * 1024


def _require_external_chat_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> None:
    configured_key = os.getenv("EXTERNAL_CHAT_API_KEY", "").strip()
    if not configured_key:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "external_chat_not_configured",
                "message": "External chat API key is not configured.",
            },
        )
    provided_key = (x_api_key or "").strip()
    if not provided_key or not hmac.compare_digest(provided_key, configured_key):
        raise HTTPException(
            status_code=401,
            detail={
                "error": "invalid_api_key",
                "message": "Valid X-API-Key header required.",
            },
        )


def _resolve_session_token(authorization: str | None, session_cookie: str | None) -> str | None:
    if isinstance(session_cookie, str) and session_cookie:
        return session_cookie
    return extract_session_token(authorization)


def _set_session_cookie(response: Response, session_token: str | None) -> None:
    if not session_token:
        return
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_token,
        max_age=SESSION_COOKIE_MAX_AGE,
        httponly=True,
        secure=SESSION_COOKIE_SECURE,
        samesite=SESSION_COOKIE_SAMESITE,
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        httponly=True,
        secure=SESSION_COOKIE_SECURE,
        samesite=SESSION_COOKIE_SAMESITE,
        path="/",
    )


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    """Attach a stable request identifier to every API request."""
    request_id = set_request_id(request.headers.get("X-Request-ID"))
    workspace_hint = request.query_params.get("workspace_id")
    request_span = start_span(
        f"HTTP {request.method} {request.url.path}",
        kind=SpanKind.SERVER,
        attributes={
            "http.method": request.method,
            "http.path": request.url.path,
            "request_id": request_id,
        },
        workspace_id=workspace_hint,
    )
    response = None
    try:
        response = await call_next(request)
        request_span.set_attribute("http.status_code", response.status_code)
        response.headers["X-Trace-ID"] = request_span.trace_id
        end_status = SpanStatus.OK if response.status_code < 500 else SpanStatus.ERROR
        from telemetry.tracing import end_span
        end_span(request_span, end_status)
    except Exception as exc:
        record_exception(request_span, exc, {"http.path": request.url.path})
        from telemetry.tracing import end_span
        end_span(request_span, SpanStatus.ERROR)
        raise
    finally:
        clear_request_id()
    if response is None:
        raise RuntimeError("response_not_available")
    response.headers["X-Request-ID"] = request_id
    return response


def _enterprise_session_from_authorization(
    authorization: str | None = Header(default=None, alias="Authorization"),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> EnterpriseSession:
    return EnterpriseSession(**get_enterprise_session(_resolve_session_token(authorization, session_cookie)))


def _coerce_session(session: object) -> EnterpriseSession:
    return coerce_session(session)


def _require_authenticated_session(session: EnterpriseSession) -> EnterpriseSession:
    return require_authenticated_session(session)


def _require_min_role(session: EnterpriseSession, role: str) -> EnterpriseSession:
    return require_min_role(session, role)


def _audit_access_denied(
    session: EnterpriseSession,
    *,
    reason: str,
    required_permission: str | None = None,
    target_type: str = "route",
    target_id: str = "unknown",
    workspace_id: str | None = None,
) -> None:
    return audit_access_denied(
        session,
        reason=reason,
        required_permission=required_permission,
        target_type=target_type,
        target_id=target_id,
        workspace_id=workspace_id,
    )


def _session_has_permission(session: EnterpriseSession, permission: str) -> bool:
    return session_has_permission(session, permission)


def _require_permission(
    session: EnterpriseSession,
    permission: str,
    *,
    workspace_id: str | None = None,
    target_type: str = "permission",
    target_id: str | None = None,
) -> EnterpriseSession:
    return require_permission(
        session,
        permission,
        workspace_id=workspace_id,
        target_type=target_type,
        target_id=target_id,
    )


def _require_admin(session: EnterpriseSession = Depends(_enterprise_session_from_authorization)) -> EnterpriseSession:
    return require_admin(session)


def _require_operator(session: EnterpriseSession = Depends(_enterprise_session_from_authorization)) -> EnterpriseSession:
    return require_operator(session)


def _require_workspace_access(
    workspace_id: str,
    session: EnterpriseSession = Depends(_enterprise_session_from_authorization),
) -> EnterpriseSession:
    return require_workspace_access(workspace_id, session)


def _resolve_workspace_scope(
    workspace_id: str | None,
    session: object,
    required_role: str | None = None,
    required_permission: str | None = None,
) -> str | None:
    return resolve_workspace_scope(
        workspace_id,
        session,
        required_role=required_role,
        required_permission=required_permission,
    )


def _current_disk_usage_percent() -> float:
    from shutil import disk_usage
    from core.config import LOGS_DIR

    usage = disk_usage(LOGS_DIR)
    return round((usage.used / usage.total) * 100, 2) if usage.total else 0.0


def _build_slo_snapshot(metrics: dict, *, workspace_id: str | None, qdrant_ok: bool) -> dict:
    """Build a human-readable SLO snapshot from the current telemetry window."""
    retrieval = metrics.get("retrieval", {})
    ingestion = metrics.get("ingestion", {})
    answer = metrics.get("answer", {})

    total_docs = float(ingestion.get("total_documents_processed", 0) or 0)
    errors = float(ingestion.get("errors", 0) or 0)
    ingestion_error_rate = round((errors / total_docs) * 100, 2) if total_docs else 0.0

    current_values = {
        "vector_store_availability": 100.0 if qdrant_ok else 0.0,
        "latency_p99": float(retrieval.get("p99_latency_ms", 0.0) or 0.0),
        "latency_p50": float(retrieval.get("p50_latency_ms", 0.0) or 0.0),
        "retrieval_latency_p99": float(retrieval.get("avg_retrieval_latency_ms", 0.0) or 0.0),
        "error_rate_ingestion": ingestion_error_rate,
        "hit_rate_top1": round(float(retrieval.get("hit_rate_top1", 0.0) or 0.0) * 100, 2),
        "hit_rate_top5": round(float(retrieval.get("hit_rate_top5", 0.0) or 0.0) * 100, 2),
        "groundedness_rate": round(float(answer.get("groundedness_rate", 0.0) or 0.0) * 100, 2),
        "no_context_rate": round(float(answer.get("no_context_rate", 0.0) or 0.0) * 100, 2),
        "disk_usage": _current_disk_usage_percent(),
    }

    items: list[dict] = []
    for slo in get_all_slos():
        current_value = float(current_values.get(slo.sli_name, 0.0) or 0.0)
        healthy, message = get_slo_status(slo.sli_name, current_value)
        sli = SLI_DEFINITIONS[slo.sli_name]
        comparator = "at_least" if slo.min_value is not None else "at_most"
        target_value = float(slo.min_value if slo.min_value is not None else slo.target_value)
        items.append(
            {
                "name": slo.sli_name,
                "description": sli.description,
                "category": sli.category.value,
                "unit": sli.unit,
                "window": slo.window,
                "current_value": current_value,
                "target_value": target_value,
                "alert_threshold": slo.alert_threshold,
                "comparator": comparator,
                "healthy": healthy,
                "status": "ok" if healthy else "breach",
                "message": message,
            }
        )

    return {
        "items": items,
        "total_breaches": sum(1 for item in items if item["status"] == "breach"),
        "workspace_id": workspace_id,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


# ─── Enterprise Session ───────────────────────────────────────


@app.get("/session", response_model=EnterpriseSession)
def get_session(session: EnterpriseSession = Depends(_enterprise_session_from_authorization)):
    """Bootstrap the current enterprise session."""
    return session


@app.get("/auth/me", response_model=EnterpriseSession)
def auth_me(session: EnterpriseSession = Depends(_enterprise_session_from_authorization)):
    """Return the current enterprise session snapshot."""
    return session


@app.get("/tenants", response_model=list[EnterpriseTenant])
def get_tenants():
    """List available tenants for the enterprise shell."""
    return list_tenants()


def _coerce_login_request(request: LoginRequest | str | None, password: str | None = None, tenant_id: str | None = None, email: str | None = None) -> LoginRequest:
    if isinstance(request, LoginRequest):
        return request
    resolved_email = request if isinstance(request, str) else email
    if isinstance(resolved_email, str):
        if not isinstance(password, str):
            raise TypeError("login() missing required password argument")
        return LoginRequest(
            email=resolved_email,
            password=password,
            tenant_id=tenant_id or "default",
        )
    raise TypeError("Invalid login request format")


@app.post("/auth/login", response_model=EnterpriseSession)
def _login_route(request: LoginRequest, response: Response, raw_request: Request):
    """Create a server-side enterprise session for the requested identity."""
    return login(request, response=response, raw_request=raw_request)


def login(
    request: LoginRequest | str | None = None,
    response: Response | str | None = None,
    raw_request: Request | str | None = None,
    *,
    email: str | None = None,
    password: str | None = None,
    tenant_id: str | None = None,
):
    """Create a server-side enterprise session for the requested identity."""
    if isinstance(request, LoginRequest):
        login_request = request
        response_obj = response
        request_obj = raw_request if isinstance(raw_request, Request) else None
    else:
        resolved_password = response if isinstance(response, str) else password
        resolved_tenant_id = raw_request if isinstance(raw_request, str) else tenant_id
        if not isinstance(resolved_password, str):
            raise TypeError("login() missing required password argument")
        login_request = _coerce_login_request(
            request,
            password=resolved_password,
            tenant_id=resolved_tenant_id,
            email=email,
        )
        response_obj = None
        request_obj = None

    with traced_span(
        "auth.login",
        kind=SpanKind.INTERNAL,
        attributes={"tenant_id": login_request.tenant_id, "email": login_request.email},
        workspace_id=login_request.tenant_id,
    ):
        try:
            session = login_enterprise_user(
                email=login_request.email,
                password=login_request.password,
                tenant_id=login_request.tenant_id,
                ip=request_obj.client.host if request_obj and request_obj.client else None,
                user_agent=request_obj.headers.get("user-agent") if request_obj else None,
            )
            if response_obj is not None:
                _set_session_cookie(response_obj, session.get("session_token"))
            log_admin_event(
                actor_user_id=session["user"]["user_id"],
                actor_email=session["user"]["email"],
                actor_role=session["user"]["role"],
                action="auth.login",
                target_type="session",
                target_id=session["session_token"],
                tenant_id=session["active_tenant"]["tenant_id"],
                metadata={"workspace_id": session["active_tenant"]["workspace_id"], "result": "success"},
            )
            return session
        except ValueError as exc:
            log_admin_event(
                actor_user_id="anonymous",
                actor_email=login_request.email,
                actor_role="anonymous",
                action="auth.login_failed",
                target_type="user",
                target_id=login_request.email,
                tenant_id=login_request.tenant_id,
                metadata={"workspace_id": login_request.tenant_id, "result": str(exc)},
            )
            raise HTTPException(status_code=401, detail={"error": "invalid_credentials", "message": "Invalid credentials"})
        except PermissionError as exc:
            log_admin_event(
                actor_user_id="anonymous",
                actor_email=login_request.email,
                actor_role="anonymous",
                action="auth.login_failed",
                target_type="user",
                target_id=login_request.email,
                tenant_id=login_request.tenant_id,
                metadata={"workspace_id": login_request.tenant_id, "result": str(exc)},
            )
            raise HTTPException(status_code=403, detail={"error": "tenant_forbidden", "message": str(exc)})


@app.post("/auth/logout", response_model=LogoutResponse)
def logout(
    authorization: str | None = Header(default=None, alias="Authorization"),
    response: Response = None,
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
):
    """Invalidate the current server-side enterprise session."""
    session_token = _resolve_session_token(authorization, session_cookie)
    current = get_enterprise_session(session_token)
    with traced_span(
        "auth.logout",
        kind=SpanKind.INTERNAL,
        attributes={"session_token": session_token or ""},
        workspace_id=current.get("active_tenant", {}).get("workspace_id"),
    ):
        logout_enterprise_session(session_token)
        if response is not None:
            _clear_session_cookie(response)
        if current.get("authenticated"):
            log_admin_event(
                actor_user_id=current["user"]["user_id"],
                actor_email=current["user"]["email"],
                actor_role=current["user"]["role"],
                action="auth.logout",
                target_type="session",
                target_id=current.get("session_token") or "unknown",
                tenant_id=current["active_tenant"]["tenant_id"],
                metadata={"workspace_id": current["active_tenant"]["workspace_id"]},
            )
        return {"status": "signed_out"}


@app.post("/auth/switch-tenant", response_model=EnterpriseSession)
def auth_switch_tenant(
    request: TenantSwitchRequest,
    authorization: str | None = Header(default=None, alias="Authorization"),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    _session: EnterpriseSession = Depends(_enterprise_session_from_authorization),
):
    """Switch the active tenant inside the current server-side session."""
    _require_authenticated_session(_session)
    with traced_span(
        "auth.switch_tenant",
        kind=SpanKind.INTERNAL,
        attributes={"tenant_id": request.tenant_id},
        workspace_id=request.tenant_id,
    ):
        try:
            switched = switch_enterprise_tenant(_resolve_session_token(authorization, session_cookie), request.tenant_id)
            log_admin_event(
                actor_user_id=_session.user.user_id,
                actor_email=_session.user.email,
                actor_role=_session.user.role,
                action="auth.switch_tenant",
                target_type="tenant",
                target_id=request.tenant_id,
                tenant_id=request.tenant_id,
                metadata={"workspace_id": switched["active_tenant"]["workspace_id"]},
            )
            return switched
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail={"error": "tenant_forbidden", "message": str(exc)})


@app.post("/auth/recovery", response_model=RecoveryResponse)
def recovery(request: RecoveryRequest):
    """Queue an access recovery request."""
    with traced_span(
        "auth.recovery",
        kind=SpanKind.INTERNAL,
        attributes={"email": request.email, "tenant_id": request.tenant_id or ""},
        workspace_id=request.tenant_id,
    ):
        return queue_recovery(request.email, request.tenant_id, request.reason)


@app.post("/auth/request-password-reset", response_model=RecoveryResponse)
def auth_request_password_reset(request: PasswordResetRequestPayload):
    """Queue a password reset request with a neutral response."""
    result = request_password_reset(request.email, request.tenant_id)
    log_admin_event(
        actor_user_id="anonymous",
        actor_email=request.email.strip().lower(),
        actor_role="anonymous",
        action="auth.password_reset_requested",
        target_type="user",
        target_id=request.email.strip().lower(),
        tenant_id=request.tenant_id,
        metadata={"workspace_id": request.tenant_id},
    )
    return result


@app.post("/auth/confirm-password-reset", response_model=RecoveryResponse)
def auth_confirm_password_reset(request: PasswordResetConfirmRequest):
    """Confirm a password reset using a one-time token."""
    try:
        result = confirm_password_reset(request.token, request.new_password)
        log_admin_event(
            actor_user_id=result["user_id"],
            actor_email="",
            actor_role="anonymous",
            action="auth.password_reset_confirmed",
            target_type="user",
            target_id=result["user_id"],
        )
        return {"status": "queued", "message": result["message"]}
    except ValueError:
        log_admin_event(
            actor_user_id="anonymous",
            actor_email="",
            actor_role="anonymous",
            action="auth.password_reset_invalid_token",
            target_type="reset_token",
            target_id="invalid",
        )
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_or_expired_reset_token", "message": "Reset token inválido ou expirado"},
        )


@app.post("/auth/change-password", response_model=RecoveryResponse)
def auth_change_password(
    request: PasswordChangeRequest,
    authorization: str | None = Header(default=None, alias="Authorization"),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    _session: EnterpriseSession = Depends(_enterprise_session_from_authorization),
):
    """Change the password for the authenticated user and revoke existing sessions."""
    session = _require_authenticated_session(_session)
    from services.enterprise_service import change_password as change_enterprise_password

    try:
        change_enterprise_password(
            user_id=session.user.user_id,
            current_password=request.current_password,
            new_password=request.new_password,
        )
        revoked = revoke_user_sessions(session.user.user_id, reason="password_change")
        revoke_enterprise_session(_resolve_session_token(authorization, session_cookie) or "", reason="password_change")
        log_admin_event(
            actor_user_id=session.user.user_id,
            actor_email=session.user.email,
            actor_role=session.user.role,
            action="auth.change_password",
            target_type="user",
            target_id=session.user.user_id,
            tenant_id=session.active_tenant.tenant_id,
            metadata={"workspace_id": session.active_tenant.workspace_id, "revoked_sessions": revoked},
        )
        return {"status": "queued", "message": "Senha alterada. Faça login novamente."}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": str(exc), "message": str(exc)})


@app.get("/auth/sessions", response_model=UserSessionListResponse)
def auth_list_sessions(
    authorization: str | None = Header(default=None, alias="Authorization"),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    _session: EnterpriseSession = Depends(_enterprise_session_from_authorization),
):
    """List sessions for the authenticated user."""
    session = _require_authenticated_session(_session)
    items = list_sessions_for_user(
        session.user.user_id,
        current_session_token=_resolve_session_token(authorization, session_cookie),
    )
    return {"items": items, "total": len(items)}


@app.post("/auth/sessions/revoke", response_model=SessionRevokeResponse)
def auth_revoke_sessions(
    request: SessionRevokeRequest,
    authorization: str | None = Header(default=None, alias="Authorization"),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    _session: EnterpriseSession = Depends(_enterprise_session_from_authorization),
):
    """Revoke one or more sessions for the current user or, with permission, for a target user."""
    session = _require_authenticated_session(_session)
    current_token = _resolve_session_token(authorization, session_cookie)
    target_user_id = request.user_id or session.user.user_id
    acting_on_other_user = target_user_id != session.user.user_id
    if acting_on_other_user:
        _require_permission(session, "sessions.revoke", workspace_id=session.active_tenant.workspace_id)
    reason = (request.reason or "manual_revoke").strip() or "manual_revoke"
    if request.revoke_all:
        revoked = revoke_user_sessions(target_user_id, reason=reason, exclude_session_token=None if acting_on_other_user else current_token)
    elif request.session_token:
        revoked = revoke_enterprise_session(request.session_token, reason=reason)
    else:
        revoked = revoke_enterprise_session(current_token or "", reason=reason)
    log_admin_event(
        actor_user_id=session.user.user_id,
        actor_email=session.user.email,
        actor_role=session.user.role,
        action="auth.session_revoked",
        target_type="user" if request.revoke_all or request.user_id else "session",
        target_id=target_user_id if request.revoke_all or request.user_id else (request.session_token or current_token or "unknown"),
        tenant_id=session.active_tenant.tenant_id,
        metadata={"workspace_id": session.active_tenant.workspace_id, "reason": reason, "revoked": revoked},
    )
    return {"revoked": revoked, "message": f"{revoked} sessão(ões) revogada(s)."}


@app.get("/admin/tenants", response_model=list[EnterpriseTenant])
def admin_list_tenants(_session: EnterpriseSession = Depends(_enterprise_session_from_authorization)):
    """List tenants for admin workflows."""
    _session = _require_permission(_session, "runtime.manage", workspace_id=_session.active_tenant.workspace_id)
    return list_admin_tenants()


@app.post("/admin/tenants", response_model=EnterpriseTenant, status_code=201)
def admin_create_tenant(request: EnterpriseTenantCreate, _session: EnterpriseSession = Depends(_require_admin)):
    """Create or replace a tenant record."""
    with traced_span("admin.tenant.create", kind=SpanKind.INTERNAL, workspace_id=request.workspace_id):
        try:
            tenant = create_tenant(request.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=409, detail={"error": "tenant_conflict", "message": str(exc)})
        log_admin_event(
            actor_user_id=_session.user.user_id,
            actor_email=_session.user.email,
            actor_role=_session.user.role,
            action="tenant.create",
            target_type="tenant",
            target_id=tenant["tenant_id"],
            tenant_id=tenant["tenant_id"],
            metadata={"workspace_id": tenant["workspace_id"]},
        )
        return tenant


@app.patch("/admin/tenants/{tenant_id}", response_model=EnterpriseTenant)
def admin_update_tenant(
    tenant_id: str,
    request: EnterpriseTenantUpdate,
    _session: EnterpriseSession = Depends(_require_admin),
):
    """Update a tenant record."""
    with traced_span("admin.tenant.update", kind=SpanKind.INTERNAL, workspace_id=request.workspace_id):
        try:
            tenant = update_tenant(tenant_id, request.model_dump(exclude_unset=True))
        except KeyError:
            raise HTTPException(status_code=404, detail={"error": "tenant_not_found", "tenant_id": tenant_id})
        except ValueError as exc:
            raise HTTPException(status_code=409, detail={"error": "tenant_conflict", "message": str(exc)})
        log_admin_event(
            actor_user_id=_session.user.user_id,
            actor_email=_session.user.email,
            actor_role=_session.user.role,
            action="tenant.update",
            target_type="tenant",
            target_id=tenant_id,
            tenant_id=tenant_id,
            metadata=request.model_dump(exclude_unset=True),
        )
        return tenant


@app.delete("/admin/tenants/{tenant_id}")
def admin_delete_tenant(tenant_id: str, _session: EnterpriseSession = Depends(_require_admin)):
    """Delete a tenant record."""
    with traced_span("admin.tenant.delete", kind=SpanKind.INTERNAL):
        try:
            deleted = delete_tenant(tenant_id)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail={"error": "tenant_delete_conflict", "message": str(exc)})
        if not deleted:
            raise HTTPException(status_code=404, detail={"error": "tenant_not_found", "tenant_id": tenant_id})
        log_admin_event(
            actor_user_id=_session.user.user_id,
            actor_email=_session.user.email,
            actor_role=_session.user.role,
            action="tenant.delete",
            target_type="tenant",
            target_id=tenant_id,
            tenant_id=tenant_id,
        )
        return {"status": "deleted", "tenant_id": tenant_id}


@app.get("/admin/users", response_model=list[EnterpriseUserRecord])
def admin_list_users(_session: EnterpriseSession = Depends(_require_admin)):
    """List users for admin workflows."""
    return list_users()


@app.post("/admin/users", response_model=EnterpriseUserRecord, status_code=201)
def admin_create_user(request: EnterpriseUserCreate, _session: EnterpriseSession = Depends(_require_admin)):
    """Create or replace a user record."""
    with traced_span("admin.user.create", kind=SpanKind.INTERNAL, workspace_id=request.tenant_id):
        try:
            user = create_user(request.model_dump())
        except KeyError:
            raise HTTPException(status_code=404, detail={"error": "tenant_not_found", "tenant_id": request.tenant_id})
        except ValueError as exc:
            raise HTTPException(status_code=409, detail={"error": "user_conflict", "message": str(exc)})
        log_admin_event(
            actor_user_id=_session.user.user_id,
            actor_email=_session.user.email,
            actor_role=_session.user.role,
            action="user.create",
            target_type="user",
            target_id=user["user_id"],
            tenant_id=user["tenant_id"],
            metadata={"role": user["role"], "status": user["status"]},
        )
        if user["role"] == "admin":
            log_admin_event(
                actor_user_id=_session.user.user_id,
                actor_email=_session.user.email,
                actor_role=_session.user.role,
                action="user.create_admin",
                target_type="user",
                target_id=user["user_id"],
                tenant_id=user["tenant_id"],
                metadata={"role": user["role"], "status": user["status"]},
            )
        return user


@app.patch("/admin/users/{user_id}", response_model=EnterpriseUserRecord)
def admin_update_user(
    user_id: str,
    request: EnterpriseUserUpdate,
    _session: EnterpriseSession = Depends(_require_admin),
):
    """Update a user record."""
    previous = get_user(user_id)
    with traced_span("admin.user.update", kind=SpanKind.INTERNAL, workspace_id=request.tenant_id or previous.get("tenant_id") if previous else None):
        try:
            payload = request.model_dump(exclude_unset=True)
            user = update_user(user_id, payload)
        except KeyError:
            raise HTTPException(status_code=404, detail={"error": "user_not_found", "user_id": user_id})
        except ValueError as exc:
            error_message = str(exc)
            raise HTTPException(status_code=409, detail={"error": "user_conflict", "message": error_message})
        metadata = request.model_dump(exclude_unset=True)
        log_admin_event(
            actor_user_id=_session.user.user_id,
            actor_email=_session.user.email,
            actor_role=_session.user.role,
            action="user.update",
            target_type="user",
            target_id=user_id,
            tenant_id=user["tenant_id"],
            metadata=metadata,
        )
        if previous and request.role is not None and request.role != previous.get("role"):
            log_admin_event(
                actor_user_id=_session.user.user_id,
                actor_email=_session.user.email,
                actor_role=_session.user.role,
                action="user.role_change",
                target_type="user",
                target_id=user_id,
                tenant_id=user["tenant_id"],
                metadata={
                    "old_role": previous.get("role"),
                    "new_role": request.role,
                    "approval_ticket": request.approval_ticket,
                    "approved": request.approve_sensitive_change is True,
                },
            )
        return user


@app.delete("/admin/users/{user_id}")
def admin_delete_user(user_id: str, _session: EnterpriseSession = Depends(_require_admin)):
    """Delete a user record."""
    deleted = delete_user(user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail={"error": "user_not_found", "user_id": user_id})
    log_admin_event(
        actor_user_id=_session.user.user_id,
        actor_email=_session.user.email,
        actor_role=_session.user.role,
        action="user.delete",
        target_type="user",
        target_id=user_id,
    )
    return {"status": "deleted", "user_id": user_id}


@app.post("/admin/users/{user_id}/reset-password")
def admin_reset_user_password(
    user_id: str,
    request: PasswordResetAdminRequest,
    _session: EnterpriseSession = Depends(_require_admin),
):
    """Issue a manual password reset token for a target user."""
    try:
        issued = admin_issue_password_reset(
            user_id,
            requested_by=_session.user.user_id,
            expires_in_minutes=request.expires_in_minutes,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail={"error": "user_not_found", "user_id": user_id})
    log_admin_event(
        actor_user_id=_session.user.user_id,
        actor_email=_session.user.email,
        actor_role=_session.user.role,
        action="user.password_reset_admin",
        target_type="user",
        target_id=user_id,
        tenant_id=_session.active_tenant.tenant_id,
        metadata={
            "workspace_id": _session.active_tenant.workspace_id,
            "reset_id": issued["reset_id"],
            "expires_at": issued["expires_at"],
            "reason": request.reason,
        },
    )
    return {
        "status": "issued",
        "reset_id": issued["reset_id"],
        "reset_token": issued["token"],
        "expires_at": issued["expires_at"],
    }


@app.get("/admin/events", response_model=AdminEventListResponse)
def admin_get_events(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    action: str | None = Query(default=None),
    tenant_id: str | None = Query(default=None),
    workspace_id: str | None = Query(default=None),
    _session: EnterpriseSession = Depends(_require_admin),
):
    """List recent administrative events with sanitized metadata."""
    return list_admin_events(limit=limit, offset=offset, action=action, tenant_id=tenant_id, workspace_id=workspace_id)


@app.get("/admin/alerts", response_model=ObservabilityAlertsResponse)
def admin_get_observability_alerts(
    days: int = Query(default=1, ge=1, le=30),
    workspace_id: str | None = Query(default=None),
    _session: EnterpriseSession = Depends(_require_admin),
):
    """Expose operational alerts for any workspace to admins."""
    try:
        tel = get_telemetry()
        return tel.get_alerts(days=days, workspace_id=workspace_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": "admin_observability_alerts_error", "message": str(e)})


@app.get("/admin/slo", response_model=ObservabilitySLOResponse)
def admin_get_observability_slo(
    days: int = Query(default=7, ge=1, le=90),
    workspace_id: str | None = Query(default=None),
    _session: EnterpriseSession = Depends(_require_admin),
):
    """Expose SLI/SLO status for any workspace to admins."""
    try:
        tel = get_telemetry()
        metrics = tel.get_metrics(days=days, workspace_id=workspace_id)
        try:
            client = get_client()
            client.get_collections()
            qdrant_ok = True
        except Exception:
            qdrant_ok = False
        return _build_slo_snapshot(metrics, workspace_id=workspace_id, qdrant_ok=qdrant_ok)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": "admin_observability_slo_error", "message": str(e)})


@app.get("/admin/traces", response_model=ObservabilityTraceResponse)
def admin_get_observability_traces(
    workspace_id: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    _session: EnterpriseSession = Depends(_require_admin),
):
    """Expose recent traces for any workspace to admins."""
    try:
        items = list_recent_spans(limit=limit, workspace_id=workspace_id)
        return {
            "items": items,
            "total": len(items),
            "workspace_id": workspace_id,
            "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": "admin_observability_traces_error", "message": str(e)})


@app.get("/admin/audits", response_model=AuditLogListResponse)
def admin_list_observability_audits(
    days: int = Query(default=30, ge=1, le=90),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    workspace_id: str | None = Query(default=None),
    _session: EnterpriseSession = Depends(_require_admin),
):
    """List recent corpus audits for any workspace to admins."""
    _session = _require_permission(_session, "audit.read", workspace_id=workspace_id or _session.active_tenant.workspace_id)
    try:
        tel = get_telemetry()
        return tel.list_audit_events(
            workspace_id=workspace_id,
            days=days,
            limit=limit,
            offset=offset,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": "admin_observability_audits_error", "message": str(e)})


@app.get("/admin/repairs", response_model=RepairLogListResponse)
def admin_list_observability_repairs(
    days: int = Query(default=30, ge=1, le=90),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    workspace_id: str | None = Query(default=None),
    _session: EnterpriseSession = Depends(_require_admin),
):
    """List recent corpus repairs for any workspace to admins."""
    _session = _require_permission(_session, "audit.read", workspace_id=workspace_id or _session.active_tenant.workspace_id)
    try:
        tel = get_telemetry()
        return tel.list_repair_events(
            workspace_id=workspace_id,
            days=days,
            limit=limit,
            offset=offset,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": "admin_observability_repairs_error", "message": str(e)})


@app.post("/admin/evaluation/run")
def admin_run_evaluation(
    workspace_id: str = Query(default="default"),
    run_judge: bool = Query(default=False),
    reranking: bool = Query(default=False),
    reranking_method: str | None = Query(default=None, description="Override reranking method: 'bm25f' or 'neural'"),
    query_expansion: bool = Query(default=False, description="Enable HyDE-like query expansion"),
    _session: EnterpriseSession = Depends(_enterprise_session_from_authorization),
):
    """Allow admins to run evaluation for any workspace without switching active tenant."""
    _session = _require_permission(_session, "runtime.manage", workspace_id=workspace_id)
    from services.evaluation_service import EvaluationService

    dataset_path = DATA_DIR / workspace_id / "dataset.json"
    if not dataset_path.exists():
        raise HTTPException(status_code=404, detail={"error": "dataset_not_found", "message": "Dataset não encontrado"})

    with traced_span(
        "evaluation.run.admin",
        kind=SpanKind.INTERNAL,
        attributes={"run_judge": run_judge, "reranking": reranking, "query_expansion": query_expansion},
        workspace_id=workspace_id,
    ):
        try:
            evaluator = EvaluationService()
            result = evaluator.run_evaluation(
                workspace_id=workspace_id,
                dataset_path=dataset_path,
                top_k=5,
                run_judge=run_judge,
                reranking=reranking,
                reranking_method=reranking_method,
                query_expansion=query_expansion,
            )
            log_admin_event(
                actor_user_id=_session.user.user_id,
                actor_email=_session.user.email,
                actor_role=_session.user.role,
                action="evaluation.run",
                target_type="workspace",
                target_id=workspace_id,
                tenant_id=None,
                metadata={
                    "workspace_id": workspace_id,
                    "run_judge": run_judge,
                    "reranking": reranking,
                    "reranking_method": reranking_method,
                    "query_expansion": query_expansion,
                    "hit_rate_top_5": result.get("hit_rate_top_5"),
                    "groundedness_rate": result.get("groundedness_rate"),
                },
            )
            return result
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail={"error": "dataset_not_found", "message": str(e)})
        except Exception as e:
            raise HTTPException(status_code=500, detail={"error": "evaluation_error", "message": str(e)})


@app.post("/admin/corpus/audit")
def admin_run_corpus_audit(
    workspace_id: str = Query(default="default"),
    check_embeddings: bool = Query(default=False, description="If true, validates dense vectors in Qdrant"),
    _session: EnterpriseSession = Depends(_enterprise_session_from_authorization),
):
    """Allow admins to run a corpus integrity audit for any workspace."""
    _session = _require_permission(_session, "corpus.audit", workspace_id=workspace_id)
    from services.integrity_service import audit_corpus_integrity

    with traced_span(
        "corpus.audit.admin",
        kind=SpanKind.INTERNAL,
        attributes={"check_embeddings": check_embeddings},
        workspace_id=workspace_id,
    ):
        try:
            report = audit_corpus_integrity(
                workspace_id=workspace_id,
                check_embeddings=check_embeddings,
            )
            try:
                tel = get_telemetry()
                tel.log_audit(
                    workspace_id=workspace_id,
                    total_documents=report.total_documents,
                    total_with_issues=report.total_with_issues,
                    total_ok=report.total_ok,
                    by_issue_type=report.by_issue_type,
                    recommendations=report.recommendations,
                )
            except Exception:
                pass
            log_admin_event(
                actor_user_id=_session.user.user_id,
                actor_email=_session.user.email,
                actor_role=_session.user.role,
                action="corpus.audit.run",
                target_type="workspace",
                target_id=workspace_id,
                tenant_id=None,
                metadata={
                    "workspace_id": workspace_id,
                    "check_embeddings": check_embeddings,
                    "total_documents": report.total_documents,
                    "total_with_issues": report.total_with_issues,
                    "by_issue_type": report.by_issue_type,
                },
            )
            return report
        except Exception as e:
            raise HTTPException(status_code=500, detail={"error": "admin_audit_error", "message": str(e)})


@app.post("/admin/corpus/repair/{document_id}")
def admin_repair_corpus_document(
    document_id: str,
    workspace_id: str = Query(default="default"),
    _session: EnterpriseSession = Depends(_enterprise_session_from_authorization),
):
    """Allow admins to repair a corpus document in any workspace."""
    _session = _require_permission(_session, "corpus.repair", workspace_id=workspace_id)
    from services.integrity_service import repair_document

    with traced_span("corpus.repair.admin", kind=SpanKind.INTERNAL, workspace_id=workspace_id):
        try:
            result = repair_document(
                document_id=document_id,
                workspace_id=workspace_id,
            )
            try:
                tel = get_telemetry()
                tel.log_repair(
                    document_id=document_id,
                    workspace_id=workspace_id,
                    success=result.success,
                    chunks_reindexed=result.chunks_reindexed,
                    embeddings_valid=result.embeddings_valid,
                    qdrant_restored=result.qdrant_restored,
                    message=result.message,
                )
            except Exception:
                pass
            if not result.success:
                raise HTTPException(status_code=422, detail={
                    "error": "repair_failed",
                    "document_id": document_id,
                    "message": result.message,
                })
            log_admin_event(
                actor_user_id=_session.user.user_id,
                actor_email=_session.user.email,
                actor_role=_session.user.role,
                action="corpus.repair.run",
                target_type="document",
                target_id=document_id,
                tenant_id=None,
                metadata={
                    "workspace_id": workspace_id,
                    "chunks_reindexed": result.chunks_reindexed,
                    "embeddings_valid": result.embeddings_valid,
                    "qdrant_restored": result.qdrant_restored,
                },
            )
            return result
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail={"error": "admin_repair_error", "message": str(e)})


@app.post("/admin/corpus/repair-batch")
def admin_repair_corpus_batch(
    workspace_id: str = Query(default="default"),
    limit: int = Query(default=20, ge=1, le=200),
    check_embeddings: bool = Query(default=False, description="If true, validates vectors before selecting documents to repair"),
    _session: EnterpriseSession = Depends(_enterprise_session_from_authorization),
):
    """Repair every non-ok document found by a fresh corpus audit, up to the provided limit."""
    _session = _require_permission(_session, "corpus.repair", workspace_id=workspace_id)
    from services.integrity_service import audit_corpus_integrity, repair_document

    try:
        report = audit_corpus_integrity(
            workspace_id=workspace_id,
            check_embeddings=check_embeddings,
        )
        candidates = [item for item in report.documents if item.status != "ok"][:limit]

        repaired = 0
        failed = 0
        results: list[dict] = []

        for item in candidates:
            result = repair_document(
                document_id=item.document_id,
                workspace_id=workspace_id,
            )
            try:
                tel = get_telemetry()
                tel.log_repair(
                    document_id=item.document_id,
                    workspace_id=workspace_id,
                    success=result.success,
                    chunks_reindexed=result.chunks_reindexed,
                    embeddings_valid=result.embeddings_valid,
                    qdrant_restored=result.qdrant_restored,
                    message=result.message,
                )
            except Exception:
                pass

            if result.success:
                repaired += 1
            else:
                failed += 1

            results.append(
                {
                    "document_id": item.document_id,
                    "success": result.success,
                    "chunks_reindexed": result.chunks_reindexed,
                    "embeddings_valid": result.embeddings_valid,
                    "qdrant_restored": result.qdrant_restored,
                    "message": result.message,
                }
            )

        payload = {
            "workspace_id": workspace_id,
            "attempted": len(candidates),
            "repaired": repaired,
            "failed": failed,
            "items": results,
        }

        log_admin_event(
            actor_user_id=_session.user.user_id,
            actor_email=_session.user.email,
            actor_role=_session.user.role,
            action="corpus.repair.batch",
            target_type="workspace",
            target_id=workspace_id,
            tenant_id=None,
            metadata={
                "workspace_id": workspace_id,
                "attempted": len(candidates),
                "repaired": repaired,
                "failed": failed,
                "document_ids": [item["document_id"] for item in results],
            },
        )
        return payload
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": "admin_repair_batch_error", "message": str(e)})


# ─── Document Upload ──────────────────────────────────────────


@app.post("/documents/upload", response_model=DocumentUploadResponse, status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    workspace_id: str = Form(default="default"),
    chunking_strategy: str = Form(default="recursive", description="Chunking strategy: 'recursive' or 'semantic'"),
    qdrant_collection: str = Form(default="cvg_master_rag"),
    _session: EnterpriseSession = Depends(_enterprise_session_from_authorization),
):
    """
    Upload and ingest a document (PDF, DOCX, MD, TXT).
    chunking_strategy: 'recursive' (default, paragraph-aware) or 'semantic' (sentence-based with embedding coherence).
    """
    from services.ingestion_service import VALID_CHUNKING_STRATEGIES
    from services.vector_service import validate_qdrant_collection_name
    _require_permission(_session, "documents.upload", workspace_id=workspace_id, target_type="workspace", target_id=workspace_id)
    try:
        qdrant_collection = validate_qdrant_collection_name(qdrant_collection)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_qdrant_collection",
                "message": str(e),
                "received": qdrant_collection,
            },
        )
    if chunking_strategy not in VALID_CHUNKING_STRATEGIES:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_chunking_strategy",
                "message": f"chunking_strategy must be one of: {', '.join(sorted(VALID_CHUNKING_STRATEGIES))}",
                "received": chunking_strategy,
            }
        )
    from services.ingestion_service import IngestionError, ingest_document

    _require_workspace_access(workspace_id, _session)
    with traced_span(
        "documents.upload",
        kind=SpanKind.INTERNAL,
        attributes={
            "filename": file.filename or "unknown",
            "chunking_strategy": chunking_strategy,
            "qdrant_collection": qdrant_collection,
        },
        workspace_id=workspace_id,
    ):
        # Check file extension
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in SUPPORTED_EXTENSIONS:
            _log_ingestion_failure(
                workspace_id=workspace_id,
                filename=file.filename or "unknown",
                source_type=suffix.lstrip(".") or "unknown",
                error=f"unsupported_format:{suffix}",
            )
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "unsupported_format",
                    "message": f"Formato '{suffix}' não é aceito. Formatos aceitos: {', '.join(SUPPORTED_EXTENSIONS)}",
                    "received": suffix,
                    "supported": list(SUPPORTED_EXTENSIONS)
                }
            )

        # Save file temporarily
        upload_dir = DOCUMENTS_DIR / workspace_id / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)

        file_path = upload_dir / file.filename
        try:
            received_bytes = 0
            with open(file_path, "wb") as output:
                while True:
                    chunk = await file.read(UPLOAD_STREAM_CHUNK_BYTES)
                    if not chunk:
                        break
                    received_bytes += len(chunk)
                    if received_bytes > MAX_UPLOAD_BYTES:
                        try:
                            file_path.unlink(missing_ok=True)
                        except Exception:
                            pass
                        max_mb = round(MAX_UPLOAD_BYTES / 1024 / 1024, 1)
                        received_mb = round(received_bytes / 1024 / 1024, 1)
                        _log_ingestion_failure(
                            workspace_id=workspace_id,
                            filename=file.filename or "unknown",
                            source_type=suffix.lstrip(".") or "unknown",
                            error="file_too_large",
                        )
                        raise HTTPException(
                            status_code=413,
                            detail={
                                "error": "file_too_large",
                                "message": f"Arquivo excede limite de {max_mb}MB",
                                "received_mb": received_mb,
                                "max_mb": max_mb,
                            }
                        )
                    output.write(chunk)

            if received_bytes == 0:
                _log_ingestion_failure(
                    workspace_id=workspace_id,
                    filename=file.filename or "unknown",
                    source_type=suffix.lstrip(".") or "unknown",
                    error="empty_file",
                )
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "empty_file",
                        "message": "Arquivo enviado esta vazio",
                    }
                )
        except HTTPException:
            raise
        except Exception as e:
            _log_ingestion_failure(
                workspace_id=workspace_id,
                filename=file.filename or "unknown",
                source_type=suffix.lstrip(".") or "unknown",
                error=f"upload_failed:{e}",
            )
            raise HTTPException(status_code=500, detail={"error": "upload_failed", "message": str(e)})

        # Ingest or queue heavy PDF work for an isolated worker.
        queued_for_worker = False
        try:
            from services.ingestion_job_service import (
                create_ingestion_job,
                IngestionPreflightError,
                preflight_large_ingestion,
                should_queue_pdf_upload,
                spawn_ingestion_worker,
                update_ingestion_job,
            )

            if should_queue_pdf_upload(file_path, received_bytes):
                preflight = preflight_large_ingestion(
                    source_path=file_path,
                    workspace_id=workspace_id,
                    received_bytes=received_bytes,
                )
                job = create_ingestion_job(
                    source_path=file_path,
                    workspace_id=workspace_id,
                    filename=file.filename or file_path.name,
                    source_type=suffix.lstrip(".") or "unknown",
                    chunking_strategy=chunking_strategy,
                    file_size_bytes=received_bytes,
                    preflight=preflight,
                    qdrant_collection=qdrant_collection,
                )
                try:
                    spawn_ingestion_worker(job["ingestion_id"])
                except Exception as e:
                    update_ingestion_job(
                        job["ingestion_id"],
                        status="failed",
                        finished_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                        error_code="worker_spawn_failed",
                        error_message=str(e),
                    )
                    raise
                queued_for_worker = True
                return DocumentUploadResponse(
                    document_id=job["document_id"],
                    status="queued",
                    catalog_scope="operational",
                    source_type=job["source_type"],
                    filename=job["filename"],
                    page_count=None,
                    char_count=0,
                    chunk_count=0,
                    created_at=job["created_at"],
                    chunking_strategy=chunking_strategy,
                    qdrant_collection=qdrant_collection,
                    ingestion_id=job["ingestion_id"],
                    message="Upload recebido; indexacao em processamento isolado.",
                )

            sync_job = create_ingestion_job(
                source_path=file_path,
                workspace_id=workspace_id,
                filename=file.filename or file_path.name,
                source_type=suffix.lstrip(".") or "unknown",
                chunking_strategy=chunking_strategy,
                file_size_bytes=received_bytes,
                preflight={"large_job": False},
                qdrant_collection=qdrant_collection,
            )
            update_ingestion_job(
                sync_job["ingestion_id"],
                status="processing",
                started_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                last_heartbeat_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                operational_status="running",
            )
            result = ingest_document(
                file_path, workspace_id, file.filename,
                chunking_strategy=chunking_strategy,
                ingestion_id=sync_job["ingestion_id"],
                qdrant_collection=qdrant_collection,
            )
            finished_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            update_ingestion_job(
                sync_job["ingestion_id"],
                status="committed",
                document_id=result.document_id,
                final_document_id=result.document_id,
                page_count=result.page_count,
                pages_processed=result.page_count or 0,
                chunks_written=result.chunk_count,
                qdrant_points_written=result.chunk_count,
                finished_at=finished_at,
                last_heartbeat_at=finished_at,
                last_batch_at=finished_at,
                operational_status="completed",
                operational_alerts=[],
                error_code=None,
                error_message=None,
            )
            return DocumentUploadResponse(
                **result.model_dump(exclude={"ingestion_id", "message"}),
                ingestion_id=sync_job["ingestion_id"],
                message=result.message,
            )
        except IngestionError as e:
            if "sync_job" in locals():
                failed_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                update_ingestion_job(
                    sync_job["ingestion_id"],
                    status="failed",
                    finished_at=failed_at,
                    last_heartbeat_at=failed_at,
                    operational_status="failed",
                    error_code="parse_failed",
                    error_message=str(e),
                )
            _log_ingestion_failure(
                workspace_id=workspace_id,
                filename=file.filename or "unknown",
                source_type=suffix.lstrip(".") or "unknown",
                error=f"parse_failed:{e}",
            )
            raise HTTPException(status_code=413, detail={"error": "parse_failed", "message": str(e)})
        except IngestionPreflightError as e:
            _log_ingestion_failure(
                workspace_id=workspace_id,
                filename=file.filename or "unknown",
                source_type=suffix.lstrip(".") or "unknown",
                error=f"preflight_failed:{e.error_code}",
            )
            raise HTTPException(
                status_code=e.status_code,
                detail={"error": e.error_code, "message": e.message, **e.details},
            )
        except Exception as e:
            if "sync_job" in locals():
                failed_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                update_ingestion_job(
                    sync_job["ingestion_id"],
                    status="failed",
                    finished_at=failed_at,
                    last_heartbeat_at=failed_at,
                    operational_status="failed",
                    error_code=e.__class__.__name__,
                    error_message=str(e),
                )
            _log_ingestion_failure(
                workspace_id=workspace_id,
                filename=file.filename or "unknown",
                source_type=suffix.lstrip(".") or "unknown",
                error=f"internal_error:{e}",
            )
            raise HTTPException(status_code=500, detail={"error": "internal_error", "message": str(e)})
        finally:
            # Clean up uploaded file
            if not queued_for_worker:
                try:
                    file_path.unlink()
                except Exception:
                    pass


# ─── Document Metadata ────────────────────────────────────────


@app.get("/documents/ingestion-jobs", response_model=DocumentIngestionJobListResponse)
def list_ingestion_job_statuses(
    workspace_id: str = Query(default="default"),
    limit: int = Query(default=10, ge=1, le=50),
    _session: EnterpriseSession = Depends(_enterprise_session_from_authorization),
):
    """Return recent asynchronous ingestion jobs for a workspace."""
    from services.ingestion_job_service import list_ingestion_jobs

    _require_permission(_session, "documents.read", workspace_id=workspace_id, target_type="workspace", target_id=workspace_id)
    _require_workspace_access(workspace_id, _session)
    jobs = list_ingestion_jobs(workspace_id=workspace_id, limit=limit)
    return DocumentIngestionJobListResponse(
        items=jobs,
        total=len(jobs),
        limit=limit,
        workspace_id=workspace_id,
    )


@app.get("/documents/ingestion-jobs/{ingestion_id}")
def get_ingestion_job_status(
    ingestion_id: str,
    workspace_id: str = Query(default="default"),
    _session: EnterpriseSession = Depends(_enterprise_session_from_authorization),
):
    """Return persisted status for an asynchronous ingestion job."""
    from services.ingestion_job_service import get_ingestion_job_status

    _require_permission(_session, "documents.read", workspace_id=workspace_id, target_type="workspace", target_id=workspace_id)
    _require_workspace_access(workspace_id, _session)
    job = get_ingestion_job_status(ingestion_id)
    if job is None or job.get("workspace_id") != workspace_id:
        raise HTTPException(
            status_code=404,
            detail={"error": "ingestion_job_not_found", "message": "Job de indexacao nao encontrado."},
        )
    return job


@app.get("/documents/qdrant-collections", response_model=QdrantCollectionListResponse)
def get_qdrant_collections(
    workspace_id: str = Query(default="default"),
    _session: EnterpriseSession = Depends(_enterprise_session_from_authorization),
):
    """List Qdrant collections available as upload targets."""
    _require_permission(_session, "documents.read", workspace_id=workspace_id, target_type="workspace", target_id=workspace_id)
    _require_workspace_access(workspace_id, _session)
    from core.config import QDRANT_COLLECTION
    from services.vector_service import list_qdrant_collections

    try:
        collections = list_qdrant_collections()
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail={"error": "qdrant_unavailable", "message": str(e)},
        )
    active = QDRANT_COLLECTION
    if active not in collections:
        collections = sorted([*collections, active])
    return QdrantCollectionListResponse(active_collection=active, collections=collections)


@app.get("/documents/{document_id}", response_model=DocumentMetadata)
def get_document(
    document_id: str,
    workspace_id: str = Query(default="default"),
    _session: EnterpriseSession = Depends(_enterprise_session_from_authorization),
):
    """
    Get document metadata.
    Returns full metadata as per contract (0009).
    """
    from services.document_registry import get_document_metadata

    _require_permission(_session, "documents.read", workspace_id=workspace_id, target_type="workspace", target_id=workspace_id)
    _require_workspace_access(workspace_id, _session)
    metadata = get_document_metadata(document_id, workspace_id)
    if not metadata:
        raise HTTPException(status_code=404, detail={
            "error": "document_not_found",
            "document_id": document_id
        })

    return metadata


@app.get("/documents", response_model=DocumentListResponse)
def get_documents(
    workspace_id: str = Query(default="default"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    source_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    query: str | None = Query(default=None),
    _session: EnterpriseSession = Depends(_enterprise_session_from_authorization),
):
    """List canonical documents for the workspace."""
    _require_permission(_session, "documents.read", workspace_id=workspace_id, target_type="workspace", target_id=workspace_id)
    _require_workspace_access(workspace_id, _session)
    return list_document_items(
        workspace_id=workspace_id,
        limit=limit,
        offset=offset,
        source_type=source_type,
        status=status,
        query=query,
    )


# ─── Search ───────────────────────────────────────────────────


@app.post("/search", response_model=SearchResponse)
def search(request: SearchRequest, _session: EnterpriseSession = Depends(_enterprise_session_from_authorization)):
    """
    Hybrid search (dense + sparse + RRF) in knowledge base.
    """
    _require_permission(_session, "search.execute", workspace_id=request.workspace_id, target_type="workspace", target_id=request.workspace_id)
    _require_workspace_access(request.workspace_id, _session)
    with traced_span(
        "search.execute",
        kind=SpanKind.INTERNAL,
        attributes={"query": request.query[:120], "top_k": request.top_k, "retrieval_profile": request.retrieval_profile},
        workspace_id=request.workspace_id,
    ):
        try:
            from services.search_service import execute_search
            result = execute_search(request, default_query_expansion_mode="off")
            return result
        except Exception as e:
            raise HTTPException(status_code=500, detail={"error": "retrieval_error", "message": str(e)})


# ─── Query (Search + Answer) ────────────────────────────────


@app.post("/query", response_model=QueryResponse)
def query(request: QueryRequest, _session: EnterpriseSession = Depends(_enterprise_session_from_authorization)):
    """
    Full RAG pipeline: search + generate answer with grounding.
    """
    from services.search_service import search_and_answer

    _require_permission(_session, "query.execute", workspace_id=request.workspace_id, target_type="workspace", target_id=request.workspace_id)
    _require_workspace_access(request.workspace_id, _session)
    with traced_span(
        "query.execute",
        kind=SpanKind.INTERNAL,
        attributes={
            "query": request.query[:120],
            "top_k": request.top_k,
            "query_expansion": request.query_expansion,
            "retrieval_profile": request.retrieval_profile,
        },
        workspace_id=request.workspace_id,
    ):
        try:
            result = search_and_answer(request)
            return result
        except Exception as e:
            raise HTTPException(status_code=500, detail={"error": "query_error", "message": str(e)})


@app.post("/external/chat", response_model=ExternalChatResponse)
def external_chat(
    request: ExternalChatRequest,
    _api_key: None = Depends(_require_external_chat_api_key),
):
    """
    External integration endpoint for server-to-server clinical chat access.

    Authentication is handled only by X-API-Key. The route always uses the
    validated clinical_v2 chat pipeline and does not expose retrieval debug.
    """
    from services.search_service import search_and_answer

    query_request = QueryRequest(
        query=request.question,
        workspace_id=request.workspace_id,
        top_k=request.top_k,
        threshold=request.threshold,
        retrieval_profile="clinical_v2",
        query_expansion_mode="off",
        query_expansion=False,
        reranking=False,
        reranking_method="none",
    )
    with traced_span(
        "external.chat",
        kind=SpanKind.INTERNAL,
        attributes={
            "query": request.question[:120],
            "top_k": request.top_k,
            "threshold": request.threshold,
            "retrieval_profile": "clinical_v2",
        },
        workspace_id=request.workspace_id,
    ):
        try:
            result = search_and_answer(query_request)
        except Exception as e:
            raise HTTPException(status_code=500, detail={"error": "external_chat_error", "message": str(e)})

    return ExternalChatResponse(
        answer=result.answer_markdown or result.answer,
        confidence=result.confidence,
        grounded=result.grounded,
        low_confidence=result.low_confidence,
        citation_coverage=result.citation_coverage,
        citations=result.citations,
        bibliography=result.bibliography,
        chunks_used=result.chunks_used,
        retrieval_profile="clinical_v2",
        latency_ms=result.latency_ms,
        completeness_status=result.completeness_status,
        missing_sections=result.missing_sections,
    )


# ─── Evaluation Dataset ───────────────────────────────────────


@app.get("/evaluation/dataset")
def get_dataset(
    workspace_id: str = Query(default="default"),
    _session: EnterpriseSession = Depends(_enterprise_session_from_authorization),
):
    """
    Get the evaluation dataset for the workspace.
    """
    _require_permission(_session, "observability.read", workspace_id=workspace_id, target_type="workspace", target_id=workspace_id)
    _require_workspace_access(workspace_id, _session)
    dataset_path = DATA_DIR / workspace_id / "dataset.json"

    if not dataset_path.exists():
        raise HTTPException(
            status_code=404,
            detail={
                "error": "dataset_not_found",
                "message": f"Workspace '{workspace_id}' não possui dataset operacional.",
            },
        )

    with open(dataset_path, "r", encoding="utf-8") as f:
        dataset = json.load(f)

    if not dataset.get("questions"):
        raise HTTPException(
            status_code=409,
            detail={
                "error": "dataset_empty",
                "message": f"Workspace '{workspace_id}' possui dataset vazio.",
            },
        )

    return dataset


@app.get("/queries/logs", response_model=QueryLogResponse)
def get_query_logs(
    workspace_id: str = Query(default="default"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    needs_review: bool | None = Query(default=None),
    low_confidence: bool | None = Query(default=None),
    grounded: bool | None = Query(default=None),
    min_citation_coverage: float | None = Query(default=None, ge=0.0, le=1.0),
    _session: EnterpriseSession = Depends(_enterprise_session_from_authorization),
):
    """Return recent query logs for audit and QA workflows."""
    _require_permission(_session, "audit.read", workspace_id=workspace_id, target_type="workspace", target_id=workspace_id)
    _require_workspace_access(workspace_id, _session)
    telemetry = get_telemetry()
    return telemetry.list_queries(
        workspace_id=workspace_id,
        limit=limit,
        offset=offset,
        needs_review=needs_review,
        low_confidence=low_confidence,
        grounded=grounded,
        min_citation_coverage=min_citation_coverage,
    )


@app.post("/evaluation/dataset")
def upload_dataset(
    dataset: Dataset,
    workspace_id: str = Query(default="default"),
    _session: EnterpriseSession = Depends(_enterprise_session_from_authorization),
):
    """Upload or replace evaluation dataset."""
    _require_permission(_session, "ingestion.run", workspace_id=workspace_id, target_type="workspace", target_id=workspace_id)
    _require_workspace_access(workspace_id, _session)
    dataset_dir = DATA_DIR / workspace_id
    dataset_dir.mkdir(parents=True, exist_ok=True)

    dataset_path = dataset_dir / "dataset.json"
    with open(dataset_path, "w", encoding="utf-8") as f:
        json.dump(dataset.model_dump(), f, ensure_ascii=False, indent=2)

    return {"status": "saved", "questions_count": len(dataset.questions)}

# ─── Evaluation Service & Metrics ───────────────────────


@app.get("/metrics")
def get_metrics(
    days: int = Query(default=7, ge=1, le=90),
    workspace_id: str | None = Query(default=None),
    _session: EnterpriseSession | object = Depends(_enterprise_session_from_authorization),
):
    """
    Get aggregated metrics for the last N days.
    Returns retrieval, ingestion, and answer metrics.
    """
    try:
        from services.telemetry_service import get_telemetry
        tel = get_telemetry()
        target_workspace = _resolve_workspace_scope(workspace_id, _session, required_permission="observability.read")
        return tel.get_metrics(days=days, workspace_id=target_workspace)
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": "metrics_error", "message": str(e)})




@app.post("/evaluation/run")
def run_evaluation(
    workspace_id: str = Query(default="default"),
    run_judge: bool = Query(default=False),
    reranking: bool = Query(default=False),
    reranking_method: str | None = Query(default=None, description="Override reranking method: 'bm25f' or 'neural'"),
    query_expansion: bool = Query(default=False, description="Enable HyDE-like query expansion"),
    _session: EnterpriseSession = Depends(_enterprise_session_from_authorization),
):
    """
    Run full evaluation on the dataset.
    If run_judge=true, also runs LLM Judge triage on answers.
    If reranking=true, enables reranking during retrieval (method from reranking_method or global config).
    If query_expansion=true, uses HyDE-like expansion before retrieval.
    """
    _require_permission(_session, "observability.read", workspace_id=workspace_id, target_type="workspace", target_id=workspace_id)
    _require_workspace_access(workspace_id, _session)
    from services.evaluation_service import EvaluationService

    dataset_path = DATA_DIR / workspace_id / "dataset.json"
    if not dataset_path.exists():
        raise HTTPException(status_code=404, detail={"error": "dataset_not_found", "message": "Dataset não encontrado"})

    try:
        evaluator = EvaluationService()
        result = evaluator.run_evaluation(
            workspace_id=workspace_id,
            dataset_path=dataset_path,
            top_k=5,
            run_judge=run_judge,
            reranking=reranking,
            reranking_method=reranking_method,
            query_expansion=query_expansion,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": "evaluation_error", "message": str(e)})


@app.post("/evaluation/ab")
def run_ab_evaluation(
    workspace_id: str = Query(default="default"),
    variant_method: str = Query(default="bm25f", description="Reranking method for variant: 'bm25f' or 'neural'"),
    query_expansion: bool = Query(default=False, description="Apply query expansion to variant"),
    _session: EnterpriseSession = Depends(_enterprise_session_from_authorization),
):
    """
    Run A/B comparison: baseline (no reranking) vs variant (with specified method).
    Returns structured comparison with deltas for HIT@K, latency, and score.
    variant_method: 'bm25f' or 'neural'
    """
    _require_permission(_session, "observability.read", workspace_id=workspace_id, target_type="workspace", target_id=workspace_id)
    _require_workspace_access(workspace_id, _session)
    from services.evaluation_service import EvaluationService

    dataset_path = DATA_DIR / workspace_id / "dataset.json"
    if not dataset_path.exists():
        raise HTTPException(status_code=404, detail={"error": "dataset_not_found", "message": "Dataset não encontrado"})

    if variant_method not in ("bm25f", "neural"):
        raise HTTPException(status_code=400, detail={"error": "invalid_reranking_method", "message": "variant_method must be 'bm25f' or 'neural'"})

    try:
        evaluator = EvaluationService()
        result = evaluator.run_ab_evaluation(
            workspace_id=workspace_id,
            dataset_path=dataset_path,
            top_k=5,
            run_judge=False,
            variant_method=variant_method,
            query_expansion=query_expansion,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": "ab_evaluation_error", "message": str(e)})


@app.post("/evaluation/query-expansion-ab")
def run_query_expansion_ab_evaluation(
    workspace_id: str = Query(default="default"),
    run_judge: bool = Query(default=False),
    _session: EnterpriseSession = Depends(_enterprise_session_from_authorization),
):
    """
    Run A/B comparison: baseline (no query expansion) vs variant (with HyDE expansion).
    Returns structured comparison with deltas for HIT@K, latency, and score.
    """
    _require_permission(_session, "observability.read", workspace_id=workspace_id, target_type="workspace", target_id=workspace_id)
    _require_workspace_access(workspace_id, _session)
    from services.evaluation_service import EvaluationService

    dataset_path = DATA_DIR / workspace_id / "dataset.json"
    if not dataset_path.exists():
        raise HTTPException(status_code=404, detail={"error": "dataset_not_found", "message": "Dataset não encontrado"})

    try:
        evaluator = EvaluationService()
        result = evaluator.run_query_expansion_ab_evaluation(
            workspace_id=workspace_id,
            dataset_path=dataset_path,
            top_k=5,
            run_judge=run_judge,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": "query_expansion_ab_error", "message": str(e)})


@app.post("/evaluation/chunking-ab")
def run_chunking_ab_evaluation(
    document_id: str = Query(..., description="Document ID to compare chunking strategies for"),
    workspace_id: str = Query(default="default"),
    run_judge: bool = Query(default=False),
    _session: EnterpriseSession = Depends(_enterprise_session_from_authorization),
):
    """
    Run A/B comparison between recursive and semantic chunking for a single document.

    Baseline: recursive chunking (original)
    Variant: semantic chunking

    The corpus is always restored to recursive chunking at the end.
    Returns structured comparison with HIT@K, latency, chunk_count, and winner.

    Limitations:
    - Only evaluates documents that exist in the corpus.
    - Requires a dataset.json in the workspace.
    - Semantic chunking fallback (offline) may produce different chunk_count.
    """
    _require_permission(_session, "corpus.audit", workspace_id=workspace_id, target_type="workspace", target_id=workspace_id)
    _require_workspace_access(workspace_id, _session)

    from core.config import DOCUMENTS_DIR
    doc_dir = DOCUMENTS_DIR / workspace_id
    raw_path = doc_dir / f"{document_id}_raw.json"
    if not raw_path.exists():
        raise HTTPException(status_code=404, detail={
            "error": "document_not_found",
            "message": f"Document {document_id} not found in workspace {workspace_id}",
        })

    dataset_path = DATA_DIR / workspace_id / "dataset.json"
    if not dataset_path.exists():
        raise HTTPException(status_code=404, detail={
            "error": "dataset_not_found",
            "message": "Dataset não encontrado",
        })

    try:
        from services.evaluation_service import EvaluationService
        evaluator = EvaluationService()
        result = evaluator.run_chunking_ab_evaluation(
            document_id=document_id,
            workspace_id=workspace_id,
            dataset_path=dataset_path,
            top_k=5,
            run_judge=run_judge,
        )
        return result
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail={
            "error": "chunking_ab_error",
            "message": str(e),
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail={
            "error": "chunking_ab_error",
            "message": str(e),
        })


# ─── Corpus Integrity ────────────────────────────────────────


@app.get("/corpus/audit")
def get_corpus_audit(
    workspace_id: str = Query(default="default"),
    check_embeddings: bool = Query(default=False, description="If true, reads and validates embedding vectors from Qdrant (expensive for large corpora)"),
    _session: EnterpriseSession | object = Depends(_enterprise_session_from_authorization),
):
    """
    Run a full corpus integrity audit for a workspace.

    Checks registry vs Qdrant consistency:
    - Documents present in registry but missing from Qdrant
    - Chunk count mismatches between registry and Qdrant
    - Invalid or corrupt embeddings in Qdrant (if check_embeddings=True)
    - Duplicate chunk_ids within the same document
    - Strategy mismatches between registry and Qdrant
    - Orphan points in Qdrant (no registry entry)

    Returns a structured CorpusIntegrityReport with per-document results and recommendations.
    """
    from services.integrity_service import audit_corpus_integrity

    target_workspace = _resolve_workspace_scope(workspace_id, _session, required_permission="corpus.audit")
    try:
        report = audit_corpus_integrity(
            workspace_id=target_workspace,
            check_embeddings=check_embeddings,
        )
        # Log the audit event
        try:
            tel = get_telemetry()
            tel.log_audit(
                workspace_id=target_workspace,
                total_documents=report.total_documents,
                total_with_issues=report.total_with_issues,
                total_ok=report.total_ok,
                by_issue_type=report.by_issue_type,
                recommendations=report.recommendations,
            )
        except Exception:
            pass
        return report
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": "audit_error", "message": str(e)})


@app.post("/corpus/repair/{document_id}")
def repair_corpus_document(
    document_id: str,
    workspace_id: str = Query(default="default"),
    _session: EnterpriseSession = Depends(_enterprise_session_from_authorization),
):
    """
    Repair a single document by re-reading its chunks from disk and re-indexing in Qdrant.

    Uses the current chunking strategy from the registry (or 'recursive' if unknown).
    After repair, Qdrant and disk should be consistent for this document.
    """
    from services.integrity_service import repair_document

    target_workspace = _resolve_workspace_scope(workspace_id, _session, required_permission="corpus.repair")
    try:
        result = repair_document(
            document_id=document_id,
            workspace_id=target_workspace,
        )
        # Log the repair event
        try:
            tel = get_telemetry()
            tel.log_repair(
                document_id=document_id,
                workspace_id=target_workspace,
                success=result.success,
                chunks_reindexed=result.chunks_reindexed,
                embeddings_valid=result.embeddings_valid,
                qdrant_restored=result.qdrant_restored,
                message=result.message,
            )
        except Exception:
            pass
        if not result.success:
            raise HTTPException(status_code=422, detail={
                "error": "repair_failed",
                "document_id": document_id,
                "message": result.message,
            })
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": "repair_error", "message": str(e)})


# ─── Error Handlers ───────────────────────────────────────────


@app.exception_handler(ValidationError)
def validation_exception_handler(_request, e):
    return JSONResponse(status_code=422, content={"error": "validation_error", "message": str(e)})


def _log_ingestion_failure(
    workspace_id: str,
    filename: str,
    source_type: str,
    error: str,
):
    """Log failed upload/parse attempts for Gate F0 observability."""
    try:
        get_telemetry().log_ingestion(
            document_id="",
            workspace_id=workspace_id,
            source_type=source_type or "unknown",
            filename=filename or "unknown",
            status="error",
            chunk_count=0,
            processing_time_ms=0,
            error=error,
        )
    except Exception:
        pass


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
