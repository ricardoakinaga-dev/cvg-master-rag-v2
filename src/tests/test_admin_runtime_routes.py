import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

SRC_DIR = Path(__file__).parent.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from api.admin_runtime_routes import (
    admin_cleanup_operational_uploads,
    admin_get_runtime,
    admin_prune_workspace_index,
)
from api.main import app
from services.admin_service import reset_admin_state


def enterprise_headers(
    client,
    role: str = "admin",
    tenant_id: str = "default",
    email: str | None = None,
) -> dict[str, str]:
    resolved_email = email or {
        "admin": "admin@demo.local",
        "operator": "operator@demo.local",
        "viewer": "viewer@demo.local",
    }.get(role, "viewer@demo.local")
    response = client.post(
        "/auth/login",
        json={
            "email": resolved_email,
            "password": "demo1234",
            "tenant_id": tenant_id,
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["session_token"]
    return {"Authorization": f"Bearer {payload['session_token']}"}


@pytest.fixture(autouse=True)
def reset_enterprise_runtime_state():
    reset_admin_state()
    yield


def test_admin_runtime_endpoint_returns_operational_summary_per_tenant(monkeypatch):
    assert callable(admin_get_runtime)

    tenants = [
        {"tenant_id": "default", "name": "Workspace Principal", "workspace_id": "default", "plan": "enterprise", "status": "active", "document_count": 5},
        {"tenant_id": "acme-lab", "name": "Acme Lab", "workspace_id": "acme-lab", "plan": "business", "status": "active", "document_count": 1},
        {"tenant_id": "northwind", "name": "Northwind Pilot", "workspace_id": "northwind", "plan": "starter", "status": "active", "document_count": 1},
    ]
    corpus_by_workspace = {
        "default": {"workspace_id": "default", "documents": 5, "chunks": 11, "parsed_documents": 5, "partial_documents": 0, "operational_documents": 0, "operational_chunks": 0},
        "acme-lab": {"workspace_id": "acme-lab", "documents": 1, "chunks": 1, "parsed_documents": 1, "partial_documents": 0, "operational_documents": 1, "operational_chunks": 2},
        "northwind": {"workspace_id": "northwind", "documents": 1, "chunks": 1, "parsed_documents": 1, "partial_documents": 0, "operational_documents": 0, "operational_chunks": 0},
    }
    snapshots = {
        "default": {
            "queries": {"latest_timestamp": "2026-04-19T12:00:00Z"},
            "ingestion": {"latest_timestamp": "2026-04-19T11:30:00Z"},
            "evaluation": {"latest_timestamp": "2026-04-19T11:45:00Z"},
        },
        "acme-lab": {
            "queries": {"latest_timestamp": "2026-04-19T10:00:00Z"},
            "ingestion": {"latest_timestamp": None},
            "evaluation": {"latest_timestamp": None},
        },
        "northwind": {
            "queries": {"latest_timestamp": "2026-04-19T09:00:00Z"},
            "ingestion": {"latest_timestamp": "2026-04-19T08:30:00Z"},
            "evaluation": {"latest_timestamp": None},
        },
    }
    alerts = {
        "default": {"total_active": 0, "items": []},
        "acme-lab": {
            "total_active": 2,
            "items": [
                {"status": "firing", "severity": "critical"},
                {"status": "firing", "severity": "high"},
            ],
        },
        "northwind": {
            "total_active": 0,
            "items": [],
        },
    }
    audits = {"default": 3, "acme-lab": 1, "northwind": 0}
    repairs = {"default": 1, "acme-lab": 0, "northwind": 2}
    qdrant_drift = {
        "default": {
            "workspace_id": "default",
            "total_points": 11,
            "canonical_points": 11,
            "noncanonical_points": 0,
            "noncanonical_documents": 0,
            "noncanonical_document_ids": [],
            "generated_at": "2026-04-19T12:30:00Z",
        },
        "acme-lab": {
            "workspace_id": "acme-lab",
            "total_points": 3,
            "canonical_points": 1,
            "noncanonical_points": 2,
            "noncanonical_documents": 1,
            "noncanonical_document_ids": ["upload-smoke-doc"],
            "generated_at": "2026-04-19T12:30:00Z",
        },
        "northwind": {
            "workspace_id": "northwind",
            "total_points": 1,
            "canonical_points": 1,
            "noncanonical_points": 0,
            "noncanonical_documents": 0,
            "noncanonical_document_ids": [],
            "generated_at": "2026-04-19T12:30:00Z",
        },
    }
    retention = {
        "default": {
            "retention_mode": "keep_latest",
            "retention_hours": 24,
            "eligible_documents": 0,
            "eligible_chunks": 0,
            "oldest_eligible_created_at": None,
        },
        "acme-lab": {
            "retention_mode": "keep_latest",
            "retention_hours": 24,
            "eligible_documents": 1,
            "eligible_chunks": 2,
            "oldest_eligible_created_at": "2026-04-18T10:00:00Z",
        },
        "northwind": {
            "retention_mode": "keep_all",
            "retention_hours": 72,
            "eligible_documents": 0,
            "eligible_chunks": 0,
            "oldest_eligible_created_at": None,
        },
    }
    metrics = {
        "default": {
            "retrieval": {"p95_latency_ms": 180.0},
            "answer": {"groundedness_rate": 1.0, "no_context_rate": 0.0},
            "evaluation": {"hit_rate_top5": 1.0},
        },
        "acme-lab": {
            "retrieval": {"p95_latency_ms": 5600.0},
            "answer": {"groundedness_rate": 0.62, "no_context_rate": 0.34},
            "evaluation": {"hit_rate_top5": 0.70},
        },
        "northwind": {
            "retrieval": {"p95_latency_ms": 1800.0},
            "answer": {"groundedness_rate": 0.82, "no_context_rate": 0.08},
            "evaluation": {"hit_rate_top5": 0.86},
        },
    }

    class FakeTelemetry:
        def get_operational_snapshot(self, days=1, workspace_id=None):
            return {"period_days": days, "workspace_id": workspace_id, **snapshots[workspace_id]}

        def get_metrics(self, days=7, workspace_id=None):
            return {"period_days": days, "workspace_id": workspace_id, **metrics[workspace_id]}

        def get_alerts(self, days=1, workspace_id=None):
            return {"workspace_id": workspace_id, "period_days": days, "generated_at": "2026-04-19T12:30:00Z", **alerts[workspace_id]}

        def list_audit_events(self, workspace_id=None, days=30, limit=20, offset=0):
            return {"items": [], "total": audits[workspace_id], "limit": limit, "offset": offset, "workspace_id": workspace_id}

        def list_repair_events(self, workspace_id=None, days=30, limit=20, offset=0):
            return {"items": [], "total": repairs[workspace_id], "limit": limit, "offset": offset, "workspace_id": workspace_id}

    monkeypatch.setattr("api.admin_runtime_routes.list_admin_tenants", lambda: tenants)
    monkeypatch.setattr("api.admin_runtime_routes.get_workspace_inventory", lambda workspace_id: corpus_by_workspace[workspace_id])
    monkeypatch.setattr("api.admin_runtime_routes.get_telemetry", lambda: FakeTelemetry())
    monkeypatch.setattr("api.admin_runtime_routes.get_client", lambda: SimpleNamespace(get_collections=lambda: SimpleNamespace(collections=[])))
    monkeypatch.setattr(
        "api.admin_runtime_routes.summarize_workspace_index_drift",
        lambda workspace_id: SimpleNamespace(model_dump=lambda: qdrant_drift[workspace_id]),
    )
    monkeypatch.setattr(
        "api.admin_runtime_routes.summarize_operational_retention",
        lambda workspace_id: SimpleNamespace(**{"workspace_id": workspace_id, "generated_at": "2026-04-19T12:30:00Z", **retention[workspace_id]}),
    )

    client = TestClient(app)
    headers = enterprise_headers(client, role="admin", tenant_id="default")

    response = client.get("/admin/runtime", headers=headers)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total"] == 3
    assert payload["qdrant_collection"] == "rag_phase0"

    by_tenant = {item["tenant_id"]: item for item in payload["items"]}
    assert by_tenant["default"]["document_count"] == 5
    assert by_tenant["default"]["chunk_count"] == 11
    assert by_tenant["default"]["qdrant_points"] == 11
    assert by_tenant["default"]["qdrant_canonical_points"] == 11
    assert by_tenant["default"]["qdrant_noncanonical_points"] == 0
    assert by_tenant["default"]["operational_documents"] == 0
    assert by_tenant["default"]["operational_cleanup_eligible_documents"] == 0
    assert by_tenant["default"]["alerts_active"] == 0
    assert by_tenant["default"]["readiness_status"] == "ready"
    assert by_tenant["default"]["readiness_score"] == 100
    assert by_tenant["acme-lab"]["operational_documents"] == 1
    assert by_tenant["acme-lab"]["operational_chunks"] == 2
    assert by_tenant["acme-lab"]["operational_retention_mode"] == "keep_latest"
    assert by_tenant["acme-lab"]["operational_retention_hours"] == 24
    assert by_tenant["acme-lab"]["operational_cleanup_eligible_documents"] == 1
    assert by_tenant["acme-lab"]["operational_cleanup_eligible_chunks"] == 2
    assert by_tenant["acme-lab"]["qdrant_noncanonical_points"] == 2
    assert by_tenant["acme-lab"]["qdrant_noncanonical_documents"] == 1
    assert by_tenant["acme-lab"]["critical_alerts"] == 1
    assert by_tenant["acme-lab"]["audit_events_30d"] == 1
    assert by_tenant["acme-lab"]["readiness_status"] == "critical"
    assert by_tenant["acme-lab"]["readiness_score"] < 55
    assert "drift vetorial" in " ".join(by_tenant["acme-lab"]["readiness_reasons"])
    assert "alertas críticos" in by_tenant["acme-lab"]["readiness_reasons"][0] or "alertas críticos" in " ".join(by_tenant["acme-lab"]["readiness_reasons"])
    assert by_tenant["northwind"]["repair_events_30d"] == 2
    assert by_tenant["northwind"]["latest_ingestion_at"] == "2026-04-19T08:30:00Z"
    assert by_tenant["northwind"]["readiness_status"] == "stable"


def test_admin_runtime_endpoint_requires_admin_role():
    client = TestClient(app)
    headers = enterprise_headers(client, role="operator", tenant_id="default")

    response = client.get("/admin/runtime", headers=headers)

    assert response.status_code == 403, response.text


def test_admin_runtime_prune_index_allows_foreign_workspace_without_switching(monkeypatch):
    assert callable(admin_prune_workspace_index)

    fake_result = SimpleNamespace(
        workspace_id="northwind",
        deleted_points=2,
        deleted_documents=1,
        deleted_document_ids=["upload-smoke-doc"],
        canonical_points_remaining=1,
        total_points_remaining=1,
        generated_at="2026-04-19T12:30:00Z",
    )

    monkeypatch.setattr("services.integrity_service.prune_workspace_index_to_registry", lambda workspace_id: fake_result)

    client = TestClient(app)
    headers = enterprise_headers(client, role="admin", tenant_id="default")

    response = client.post("/admin/runtime/prune-index?workspace_id=northwind", headers=headers)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["workspace_id"] == "northwind"
    assert payload["deleted_points"] == 2
    assert payload["deleted_documents"] == 1


def test_admin_runtime_prune_index_requires_admin_role():
    client = TestClient(app)
    headers = enterprise_headers(client, role="operator", tenant_id="default")

    response = client.post("/admin/runtime/prune-index?workspace_id=acme-lab", headers=headers)

    assert response.status_code == 403, response.text


def test_admin_runtime_cleanup_operational_allows_foreign_workspace_without_switching(monkeypatch):
    assert callable(admin_cleanup_operational_uploads)

    fake_result = SimpleNamespace(
        workspace_id="northwind",
        retention_mode="keep_all",
        retention_hours=72,
        deleted_documents=2,
        deleted_chunks=5,
        deleted_document_ids=["upload-1", "upload-2"],
        remaining_operational_documents=1,
        remaining_operational_chunks=1,
        generated_at="2026-04-19T12:30:00Z",
    )

    monkeypatch.setattr("services.operational_retention_service.cleanup_operational_uploads", lambda workspace_id: fake_result)

    client = TestClient(app)
    headers = enterprise_headers(client, role="admin", tenant_id="default")

    response = client.post("/admin/runtime/cleanup-operational?workspace_id=northwind", headers=headers)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["workspace_id"] == "northwind"
    assert payload["deleted_documents"] == 2
    assert payload["deleted_chunks"] == 5


def test_admin_runtime_cleanup_operational_requires_admin_role():
    client = TestClient(app)
    headers = enterprise_headers(client, role="operator", tenant_id="default")

    response = client.post("/admin/runtime/cleanup-operational?workspace_id=acme-lab", headers=headers)

    assert response.status_code == 403, response.text
