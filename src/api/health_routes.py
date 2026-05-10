from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from qdrant_client.models import FieldCondition, Filter, MatchValue

from core.config import QDRANT_COLLECTION
from models.schemas import EnterpriseSession
from services.api_security import enterprise_session_from_authorization, resolve_workspace_scope
from services.document_registry import get_workspace_inventory
from services.telemetry_service import get_telemetry
from services.vector_service import get_client
from telemetry.tracing import SpanKind, traced_span

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check(
    workspace_id: str | None = Query(default=None),
    light: bool = Query(default=False),
    session: EnterpriseSession | object = Depends(enterprise_session_from_authorization),
):
    """Health check endpoint."""
    target_workspace = resolve_workspace_scope(workspace_id, session)
    with traced_span("health.check", kind=SpanKind.INTERNAL, workspace_id=target_workspace) as span:
        light_enabled = light is True
        corpus = None
        telemetry_snapshot = None
        if not light_enabled:
            corpus = get_workspace_inventory(target_workspace or "default")
            telemetry_snapshot = get_telemetry().get_operational_snapshot(days=1, workspace_id=target_workspace)
        qdrant_ok = False
        qdrant_points = None
        qdrant_workspace_points = None
        try:
            client = get_client()
            client.get_collections()
            if not light_enabled:
                try:
                    qdrant_points = client.count(
                        collection_name=QDRANT_COLLECTION,
                        exact=True,
                    ).count
                    qdrant_workspace_points = client.count(
                        collection_name=QDRANT_COLLECTION,
                        count_filter=Filter(
                            must=[
                                FieldCondition(
                                    key="workspace_id",
                                    match=MatchValue(value=target_workspace),
                                )
                            ]
                        ),
                        exact=True,
                    ).count
                except Exception:
                    qdrant_points = None
                    qdrant_workspace_points = None
            qdrant_ok = True
        except Exception:
            pass

        span.set_attribute("qdrant.ok", qdrant_ok)
        span.set_attribute("workspace_id", target_workspace or "default")
        span.set_attribute("health.light", light_enabled)
        return {
            "status": "healthy" if qdrant_ok else "degraded",
            "version": "0.1.0",
            "workspace_id": target_workspace,
            "mode": "light" if light_enabled else "full",
            "qdrant": {
                "status": "ok" if qdrant_ok else "error",
                "collection": QDRANT_COLLECTION,
                "points": qdrant_points,
                "workspace_points": qdrant_workspace_points,
            },
            "corpus": corpus,
            "telemetry": telemetry_snapshot,
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
