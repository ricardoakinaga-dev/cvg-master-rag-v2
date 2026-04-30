"""Route-level security helpers for API endpoints.

Centraliza dependências de sessão e autorização usadas por rotas do FastAPI.
"""

from __future__ import annotations

from fastapi import Cookie, Depends, Header

from models.schemas import EnterpriseSession
from services.api_security import (
    audit_access_denied,
    coerce_session,
    require_admin,
    require_authenticated_session,
    require_min_role,
    require_operator,
    require_permission,
    require_workspace_access,
    resolve_workspace_scope,
    session_has_permission,
)
from services.enterprise_service import SESSION_COOKIE_NAME, bootstrap_session, extract_session_token, get_session as get_enterprise_session


def resolve_session_token(authorization: str | None = Header(default=None, alias="Authorization"), session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME)) -> str | None:
    return session_cookie or extract_session_token(authorization)


def enterprise_session_from_authorization(
    authorization: str | None = Header(default=None, alias="Authorization"),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> EnterpriseSession:
    return EnterpriseSession(**get_enterprise_session(resolve_session_token(authorization, session_cookie)))


def _coerce_session(session: object) -> EnterpriseSession:
    return coerce_session(session)


def _resolve_session_token(authorization: str | None, session_cookie: str | None) -> str | None:
    return resolve_session_token(authorization, session_cookie)


def _enterprise_session_from_authorization(
    authorization: str | None = Header(default=None, alias="Authorization"),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> EnterpriseSession:
    return enterprise_session_from_authorization(authorization=authorization, session_cookie=session_cookie)


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
