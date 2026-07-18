"""AutoDivergenceLakeWriter：Mock MinIO / PG，覆盖成功与 PG 失败补偿路径。"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from minio import Minio

from src.adapters.storage.data_lake_sample_store import AutoDivergenceLakeWriter, DataLakeWriteError
from src.adapters.storage.minio_client import MinioStorageClient
from src.types.frames import ConfidenceLevel, UncertainFrameUpload
from src.types.models import VlmComplianceVerdict


def _upload() -> UncertainFrameUpload:
    return UncertainFrameUpload(
        workstation_id="ws-1",
        sop_id="sop-uuid-1",
        sop_step=2,
        captured_at=datetime(2026, 4, 14, 8, 0, 0, tzinfo=timezone.utc),
        edge_confidence=0.55,
        edge_level=ConfidenceLevel.UNCERTAIN,
        frame_jpeg=b"\xff\xd8\xff\xe0",
        fsm_state="S2",
    )


def test_minio_upload_failure_surfaces_as_data_lake_write_error() -> None:
    async def _run() -> None:
        minio = AsyncMock(spec=MinioStorageClient)
        minio.upload_hard_case_jpeg = AsyncMock(side_effect=OSError("minio unreachable"))
        pg = AsyncMock()
        writer = AutoDivergenceLakeWriter(minio, pg, minio_uri_prefix="minio://")
        with pytest.raises(DataLakeWriteError) as ei:
            await writer.save_auto_divergence(
                upload=_upload(),
                vlm_verdict=VlmComplianceVerdict(is_anomaly=True, reason="", confidence=0.5),
                reason_code="X",
            )
        assert "MinIO" in str(ei.value)
        assert isinstance(ei.value.__cause__, OSError)
        pg.insert_auto_sample.assert_not_awaited()

    asyncio.run(_run())


def test_minio_hard_case_upload_requires_bucket_config() -> None:
    raw = MagicMock(spec=Minio)
    client = MinioStorageClient(raw, "kf", "vid", hard_cases_bucket=None)
    with pytest.raises(ValueError, match="hard_cases_bucket"):
        asyncio.run(
            client.upload_hard_case_jpeg(
                workstation_id="w",
                captured_at=datetime.now(timezone.utc),
                image_bytes=b"x",
            ),
        )


def test_save_auto_divergence_success() -> None:
    async def _run() -> str:
        minio = AsyncMock(spec=MinioStorageClient)
        minio.upload_hard_case_jpeg = AsyncMock(return_value="hard-cases/ws-1/2026/04/14/x.jpg")
        minio.remove_object_at_storage_path = AsyncMock()
        pg = AsyncMock()
        pg.insert_auto_sample = AsyncMock()
        writer = AutoDivergenceLakeWriter(minio, pg, minio_uri_prefix="minio://")
        vlm = VlmComplianceVerdict(is_anomaly=True, reason="x", confidence=0.9)
        path = await writer.save_auto_divergence(
            upload=_upload(),
            vlm_verdict=vlm,
            reason_code="EDGE_COMPLIANT_VLM_ANOMALY",
        )
        minio.upload_hard_case_jpeg.assert_awaited_once()
        pg.insert_auto_sample.assert_awaited_once()
        kw = pg.insert_auto_sample.await_args.kwargs
        assert kw["frame_path"] == path
        assert kw["label"] == "ANOMALY"
        assert kw["source"] == "auto"
        assert kw["sop_step"] == 2
        assert kw["workstation_id"] == "ws-1"
        assert kw["sop_id"] == "sop-uuid-1"
        assert kw["reason_code"] == "EDGE_COMPLIANT_VLM_ANOMALY"
        assert isinstance(kw["sample_id"], uuid.UUID)
        minio.remove_object_at_storage_path.assert_not_awaited()
        return path

    path = asyncio.run(_run())
    assert path == "minio://hard-cases/ws-1/2026/04/14/x.jpg"


def test_save_auto_divergence_pg_failure_triggers_minio_delete() -> None:
    async def _run() -> None:
        minio = AsyncMock(spec=MinioStorageClient)
        minio.upload_hard_case_jpeg = AsyncMock(return_value="hard-cases/ws-1/2026/04/14/y.jpg")
        minio.remove_object_at_storage_path = AsyncMock()
        pg = AsyncMock()
        pg.insert_auto_sample = AsyncMock(side_effect=RuntimeError("db down"))
        writer = AutoDivergenceLakeWriter(minio, pg, minio_uri_prefix="minio://")
        vlm = VlmComplianceVerdict(is_anomaly=False, reason="", confidence=0.2)
        with pytest.raises(DataLakeWriteError) as ei:
            await writer.save_auto_divergence(
                upload=_upload(),
                vlm_verdict=vlm,
                reason_code="EDGE_VIOLATION_VLM_CLEAR",
            )
        assert "PostgreSQL" in str(ei.value)
        assert ei.value.__cause__ is not None
        assert isinstance(ei.value.__cause__, RuntimeError)
        minio.remove_object_at_storage_path.assert_awaited_once_with("hard-cases/ws-1/2026/04/14/y.jpg")

    asyncio.run(_run())


def test_save_auto_divergence_pg_and_cleanup_fail() -> None:
    async def _run() -> None:
        minio = AsyncMock(spec=MinioStorageClient)
        minio.upload_hard_case_jpeg = AsyncMock(return_value="hard-cases/a/b.jpg")
        minio.remove_object_at_storage_path = AsyncMock(side_effect=OSError("network"))
        pg = AsyncMock()
        pg.insert_auto_sample = AsyncMock(side_effect=ValueError("unique"))
        writer = AutoDivergenceLakeWriter(minio, pg, minio_uri_prefix="minio://")
        with pytest.raises(DataLakeWriteError) as ei:
            await writer.save_auto_divergence(
                upload=_upload(),
                vlm_verdict=VlmComplianceVerdict(is_anomaly=False, reason="", confidence=0.1),
                reason_code="",
            )
        assert "孤立对象" in str(ei.value) or "storage_path" in str(ei.value)
        assert isinstance(ei.value.__cause__, ValueError)

    asyncio.run(_run())
