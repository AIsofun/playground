"""合规 HTTP 路由单测：Mock ``ComplianceQueryService``，无 PostgreSQL。"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes import compliance as compliance_routes
from src.services.compliance.compliance_query import (
    ComplianceEventsStoreError,
    ComplianceSummary,
)
from src.types.events import ComplianceEvent, EventType


@pytest.fixture
def test_app() -> FastAPI:
    app = FastAPI()
    app.include_router(compliance_routes.router, prefix="/api")
    return app


def test_compliance_health_store_not_configured(test_app: FastAPI) -> None:
    client = TestClient(test_app)
    r = client.get("/api/compliance/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["events_store_configured"] is False


def test_compliance_health_store_configured(test_app: FastAPI) -> None:
    test_app.state.compliance_query = AsyncMock()
    client = TestClient(test_app)
    r = client.get("/api/compliance/health")
    assert r.status_code == 200
    assert r.json()["events_store_configured"] is True


def test_compliance_events_503_without_query_service(test_app: FastAPI) -> None:
    client = TestClient(test_app)
    r = client.get("/api/compliance/events")
    assert r.status_code == 503
    assert r.json()["detail"]["code"] == "storage_unavailable"


def test_compliance_events_200(test_app: FastAPI) -> None:
    ev = ComplianceEvent(
        timestamp=datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc),
        workstation_id="ws-1",
        event_type=EventType.SOP_VIOLATION,
        sop_step=2,
        frame_path="minio://hard-cases/ws-1/x.jpg",
        confidence=0.42,
    )
    q = AsyncMock()
    q.list_events = AsyncMock(return_value=[ev])
    test_app.state.compliance_query = q
    client = TestClient(test_app)
    r = client.get("/api/compliance/events?limit=10")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["workstation_id"] == "ws-1"
    assert data[0]["event_type"] == "SOP_VIOLATION"
    q.list_events.assert_awaited_once()


def test_compliance_events_503_on_store_error(test_app: FastAPI) -> None:
    q = AsyncMock()
    q.list_events = AsyncMock(side_effect=ComplianceEventsStoreError("no relation"))
    test_app.state.compliance_query = q
    client = TestClient(test_app)
    r = client.get("/api/compliance/events")
    assert r.status_code == 503
    assert r.json()["detail"]["code"] == "compliance_store_unavailable"


def test_compliance_summary_200(test_app: FastAPI) -> None:
    end = datetime(2026, 4, 14, 12, 0, tzinfo=timezone.utc)
    start = datetime(2026, 4, 13, 12, 0, tzinfo=timezone.utc)
    summary = ComplianceSummary(
        window_start_utc=start,
        window_end_utc=end,
        workstation_id="ws-9",
        total_events=100,
        violation_events=5,
        compliance_rate=0.95,
    )
    q = AsyncMock()
    q.summary = AsyncMock(return_value=summary)
    test_app.state.compliance_query = q
    client = TestClient(test_app)
    r = client.get("/api/compliance/summary?workstation_id=ws-9&since_hours=24")
    assert r.status_code == 200
    body = r.json()
    assert body["total_events"] == 100
    assert body["violation_events"] == 5
    assert body["compliance_rate"] == 0.95
    assert body["workstation_id"] == "ws-9"


def test_openapi_lists_compliance_paths(test_app: FastAPI) -> None:
    client = TestClient(test_app)
    spec = client.get("/openapi.json").json()
    paths = spec["paths"]
    assert "/api/compliance/health" in paths
    assert "/api/compliance/events" in paths
    assert "/api/compliance/summary" in paths
