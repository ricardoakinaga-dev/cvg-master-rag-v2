from __future__ import annotations

from fastapi import Cookie, Depends, Header, HTTPException

from models.schemas import EnterpriseSession
from services.admin_service import log_admin_event
from services.enterprise_service import (
    SESSION_COOKIE_NAME,
    bootstrap_session,
    extract_session_token,
    get_session as get_enterprise_session,
)

ROLE_ORDER = {"viewer": 0, "operator": 1, "auditor": 2, "admin_rag": 3, "super_admin": 4, "admin": 4}


def enterprise_session_from_authorization(
    authorization: str | None = Header(default=None, alias="Authorization"),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> EnterpriseSession:
    return EnterpriseSession(**get_enterprise_session(session_cookie or extract_session_token(authorization)))


def coerce_session(session: object) -> EnterpriseSession:
    if isinstance(session, EnterpriseSession):
        return session
    return EnterpriseSession(**bootstrap_session())


def require_authenticated_session(session: EnterpriseSession) -> EnterpriseSession:
    session = coerce_session(session)
    if not session.authenticated or session.session_state != "active":
        raise HTTPException(status_code=401, detail={"error": "unauthorized", "message": "Active session required"})
    return session


def require_min_role(session: EnterpriseSession, role: str) -> EnterpriseSession:
    session = require_authenticated_session(session)
    if ROLE_ORDER.get(session.user.role, 0) < ROLE_ORDER.get(role, 0):
        raise HTTPException(status_code=403, detail={"error": "forbidden", "message": f"{role} role required"})
    return session


def audit_access_denied(
    session: EnterpriseSession,
    *,
    reason: str,
    required_permission: str | None = None,
    target_type: str = "route",
    target_id: str = "unknown",
    workspace_id: str | None = None,
) -> None:
    actor = session.user if session.authenticated else None
    log_admin_event(
        actor_user_id=actor.user_id if actor else "anonymous",
        actor_email=actor.email if actor else "",
        actor_role=actor.role if actor else "anonymous",
        action="auth.access_denied",
        target_type=target_type,
        target_id=target_id,
        tenant_id=session.active_tenant.tenant_id if session.authenticated else None,
        metadata={
            "workspace_id": workspace_id,
            "required_permission": required_permission,
            "reason": reason,
        },
    )


def session_has_permission(session: EnterpriseSession, permission: str) -> bool:
    return "*" in session.user.permissions or permission in session.user.permissions


def require_permission(
    session: EnterpriseSession,
    permission: str,
    *,
    workspace_id: str | None = None,
    target_type: str = "permission",
    target_id: str | None = None,
) -> EnterpriseSession:
    session = require_authenticated_session(coerce_session(session))
    if not session_has_permission(session, permission):
        audit_access_denied(
            session,
            reason="missing_permission",
            required_permission=permission,
            target_type=target_type,
            target_id=target_id or permission,
            workspace_id=workspace_id,
        )
        raise HTTPException(
            status_code=403,
            detail={"error": "forbidden", "message": f"Permission '{permission}' required"},
        )
    return session


def require_admin(session: EnterpriseSession = Depends(enterprise_session_from_authorization)) -> EnterpriseSession:
    return require_permission(session, "runtime.manage", target_type="permission", target_id="runtime.manage")


def require_operator(session: EnterpriseSession = Depends(enterprise_session_from_authorization)) -> EnterpriseSession:
    return require_min_role(session, "operator")


def require_workspace_access(
    workspace_id: str,
    session: EnterpriseSession = Depends(enterprise_session_from_authorization),
) -> EnterpriseSession:
    session = require_authenticated_session(coerce_session(session))
    if session.active_tenant.workspace_id != workspace_id:
        audit_access_denied(
            session,
            reason="workspace_forbidden",
            target_type="workspace",
            target_id=workspace_id,
            workspace_id=workspace_id,
        )
        raise HTTPException(
            status_code=403,
            detail={
                "error": "workspace_forbidden",
                "message": f"Workspace '{workspace_id}' is not active for tenant '{session.active_tenant.tenant_id}'",
            },
        )
    return session


def resolve_workspace_scope(
    workspace_id: str | None,
    session: object,
    required_role: str | None = None,
    required_permission: str | None = None,
) -> str | None:
    if not isinstance(workspace_id, str):
        workspace_id = None
    coerced = coerce_session(session)
    if isinstance(session, EnterpriseSession):
        if not coerced.authenticated or coerced.session_state != "active":
            return workspace_id or "default"
        if required_role:
            require_min_role(coerced, required_role)
        if required_permission:
            require_permission(coerced, required_permission, workspace_id=workspace_id or coerced.active_tenant.workspace_id)
        target_workspace = workspace_id or coerced.active_tenant.workspace_id
        require_workspace_access(target_workspace, coerced)
        return target_workspace
    return workspace_id or "default"
