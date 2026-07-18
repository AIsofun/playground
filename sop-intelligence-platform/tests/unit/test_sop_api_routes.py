"""T08 · SOP API 路由单元测试（Mock 存储与 Mock VLM，无外部服务）。"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes import sop as sop_routes
from src.services.sop_engine.vlm_annotator import MockVLMAnnotator
from src.types.sop import SOPDocument, SOPStep


@pytest.fixture
def test_app() -> FastAPI:
    app = FastAPI()
    app.include_router(sop_routes.router, prefix="/api")
    return app


@pytest.fixture
def mock_version_manager() -> AsyncMock:
    vm = AsyncMock()

    async def _save(
        doc: SOPDocument,
        *,
        keyframe_bytes: dict[int, bytes],
    ) -> SOPDocument:
        return doc

    vm.save.side_effect = _save
    vm.get = AsyncMock(return_value=None)
    return vm


def test_generate_completed(
    test_app: FastAPI,
    mock_version_manager: AsyncMock,
) -> None:
    test_app.state.version_manager = mock_version_manager
    with patch(
        "src.api.routes.sop._vlm_annotator",
        return_value=MockVLMAnnotator(),
    ):
        client = TestClient(test_app)
        r = client.post(
            "/api/sop/generate",
            json={
                "product_id": "PROD-API-1",
                "video_paths": ["minio://sop-videos/PROD-API-1/demo.mp4"],
                "version": "v1.0",
            },
        )
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "completed"
    assert data["sop_id"] == data["task_id"]
    assert data["sop_id"]
    mock_version_manager.save.assert_awaited_once()


def test_generate_503_without_version_manager(test_app: FastAPI) -> None:
    test_app.state.version_manager = None
    client = TestClient(test_app)
    r = client.post(
        "/api/sop/generate",
        json={
            "product_id": "P",
            "video_paths": ["minio://x/a.mp4"],
        },
    )
    assert r.status_code == 503
    assert r.json()["detail"]["code"] == "storage_unavailable"


def test_get_sop_404(test_app: FastAPI, mock_version_manager: AsyncMock) -> None:
    test_app.state.version_manager = mock_version_manager
    client = TestClient(test_app)
    r = client.get("/api/sop/00000000-0000-0000-0000-000000000099")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "not_found"


def test_get_sop_200(test_app: FastAPI, mock_version_manager: AsyncMock) -> None:
    doc = SOPDocument(
        sop_id="550e8400-e29b-41d4-a716-446655440000",
        product_id="P",
        version="P-v1.0",
        steps=[
            SOPStep(
                step_id=1,
                description="d",
                action_object="o",
                keyframe_path="minio://sop-keyframes/x/step_1.jpg",
                video_timestamp=0.0,
                action_type="pick_up_bolt",
                warnings=[],
            )
        ],
        total_steps=1,
        created_at=datetime.now(timezone.utc),
        source_video_paths=["minio://sop-videos/P/a.mp4"],
        status="draft",
    )
    mock_version_manager.get = AsyncMock(return_value=doc)
    test_app.state.version_manager = mock_version_manager
    client = TestClient(test_app)
    r = client.get(f"/api/sop/{doc.sop_id}")
    assert r.status_code == 200
    assert r.json()["sop_id"] == doc.sop_id


def test_generate_vlm_timeout_returns_504(test_app: FastAPI) -> None:
    class SlowAnnotator:
        async def annotate(self, *args: object, **kwargs: object) -> list:
            import asyncio

            await asyncio.sleep(3600)
            return []

    vm = AsyncMock()
    vm.save = AsyncMock()
    test_app.state.version_manager = vm

    with patch("src.api.routes.sop._vlm_annotator", return_value=SlowAnnotator()):
        with patch("src.api.routes.sop._vlm_total_timeout_sec", return_value=0.01):
            client = TestClient(test_app)
            r = client.post(
                "/api/sop/generate",
                json={
                    "product_id": "P",
                    "video_paths": ["minio://x/v.mp4"],
                },
            )
    assert r.status_code == 504
    assert r.json()["detail"]["code"] == "vlm_timeout"
    vm.save.assert_not_awaited()
