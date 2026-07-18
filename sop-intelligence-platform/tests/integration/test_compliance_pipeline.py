"""合规集成测试（MinIO+PG 数据湖；gRPC+Kafka 慢路径）。

- **数据湖**：需 ``COMPLIANCE_E2E=1``；迁移 ``003_create_data_lake_samples.sql`` 或测试内联 DDL。
- **gRPC → Kafka**：需 ``COMPLIANCE_PIPELINE_E2E=1`` 与可用 Kafka（见 ``tests/integration/README.md``）。

依赖启动方式、端口与 CI 建议见 **``tests/integration/README.md``**；Compose 文件：
``deploy/docker-compose.integration.yml``。

环境变量（数据湖，与 SOP E2E 类似，可覆盖）：

- ``COMPLIANCE_E2E_POSTGRES_DSN`` — 默认 ``postgresql://postgres:postgres@127.0.0.1:5432/postgres``
- ``COMPLIANCE_E2E_MINIO_ENDPOINT`` / ``ACCESS_KEY`` / ``SECRET_KEY`` / ``SECURE``

gRPC + Kafka 流水线：

- ``COMPLIANCE_PIPELINE_KAFKA_BOOTSTRAP`` — 默认 ``127.0.0.1:19092``（Redpanda 映射端口）
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from datetime import datetime, timezone
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import asyncpg
import pytest
from grpc import aio
from minio import Minio

from src.adapters.edge.grpc_server import create_uncertain_frame_upload_aio_server
from src.adapters.edge.proto_gen import frame_upload_pb2
from src.adapters.edge.proto_gen.frame_upload_pb2_grpc import FrameUploadServiceStub
from src.adapters.messaging.kafka_producer import ComplianceKafkaProducer
from src.adapters.storage.data_lake_sample_store import AutoDivergenceLakeWriter
from src.adapters.storage.minio_client import MinioStorageClient
from src.adapters.storage.postgres_client import PostgresDataLakeSamplesClient
from src.config.kafka import get_kafka_settings
from src.config.storage import StorageSettings
from src.services.compliance.uncertain_frame_orchestrator import (
    SlowPathDependencies,
    UncertainFrameSlowPathOrchestrator,
)
from src.types.events import ComplianceEvent
from src.types.frames import ConfidenceLevel, UncertainFrameUpload
from src.types.models import InferenceResult, VlmComplianceVerdict


def _env_dsn() -> str:
    return os.environ.get(
        "COMPLIANCE_E2E_POSTGRES_DSN",
        "postgresql://postgres:postgres@127.0.0.1:5432/postgres",
    )


def _env_minio_params() -> tuple[str, str, str, bool]:
    endpoint = os.environ.get("COMPLIANCE_E2E_MINIO_ENDPOINT", "127.0.0.1:9000")
    access = os.environ.get("COMPLIANCE_E2E_MINIO_ACCESS_KEY", "minioadmin")
    secret = os.environ.get("COMPLIANCE_E2E_MINIO_SECRET_KEY", "minioadmin")
    secure = os.environ.get("COMPLIANCE_E2E_MINIO_SECURE", "").lower() in ("1", "true", "yes")
    return endpoint, access, secret, secure


def _e2e_opt_in() -> bool:
    return os.environ.get("COMPLIANCE_E2E", "").lower() in ("1", "true", "yes", "on")


def _pipeline_e2e_opt_in() -> bool:
    return os.environ.get("COMPLIANCE_PIPELINE_E2E", "").lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _kafka_bootstrap() -> str:
    return os.environ.get(
        "COMPLIANCE_PIPELINE_KAFKA_BOOTSTRAP",
        "127.0.0.1:19092",
    )


def _probe_kafka(bootstrap: str) -> bool:
    try:
        from kafka.admin import KafkaAdminClient
    except ModuleNotFoundError:
        pytest.skip("未安装 kafka-python，无法运行 Kafka 集成测试（见 requirements.txt）")
    try:
        ac = KafkaAdminClient(bootstrap_servers=bootstrap, request_timeout_ms=4000)
        try:
            ac.list_topics()
        finally:
            ac.close()
        return True
    except Exception:
        return False


async def _probe_postgres(dsn: str) -> bool:
    try:
        conn = await asyncpg.connect(dsn, timeout=2.0)
        await conn.close()
        return True
    except Exception:
        return False


def _probe_minio(endpoint: str, access: str, secret: str, secure: bool) -> bool:
    try:
        from urllib3 import PoolManager
        from urllib3.util import Timeout

        http_client = PoolManager(timeout=Timeout(connect=2.0, read=2.0))
        c = Minio(
            endpoint,
            access_key=access,
            secret_key=secret,
            secure=secure,
            http_client=http_client,
        )
        list(c.list_buckets())
        return True
    except Exception:
        return False


async def _ensure_bucket(client: Minio, name: str) -> None:
    def _ensure() -> None:
        if not client.bucket_exists(name):
            client.make_bucket(name)

    await asyncio.to_thread(_ensure)


def _migration_sql_chunks() -> list[str]:
    """与 ``003_create_data_lake_samples.sql`` 等价、可逐条 ``execute`` 的语句列表。"""
    path = Path(__file__).resolve().parents[2] / "data" / "migrations" / "003_create_data_lake_samples.sql"
    raw = path.read_text(encoding="utf-8")
    parts: list[str] = []
    for block in raw.split(";"):
        lines = [
            ln
            for ln in block.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        body = "\n".join(lines).strip()
        if body:
            parts.append(body + ";")
    return parts


@pytest.fixture(scope="module")
def compliance_e2e_services() -> dict[str, Any]:
    if not _e2e_opt_in():
        pytest.skip("设置 COMPLIANCE_E2E=1 以运行 MinIO+PG 合规数据湖集成测试")
    dsn = _env_dsn()
    ep, ak, sk, sec = _env_minio_params()
    ok_pg = asyncio.run(_probe_postgres(dsn))
    ok_m = _probe_minio(ep, ak, sk, sec)
    if not (ok_pg and ok_m):
        pytest.skip("需要可用的 PostgreSQL 与 MinIO")
    settings = StorageSettings()
    return {
        "dsn": dsn,
        "minio_endpoint": ep,
        "minio_access": ak,
        "minio_secret": sk,
        "minio_secure": sec,
        "settings": settings,
    }


@pytest.mark.integration
def test_auto_divergence_minio_and_postgres(compliance_e2e_services: dict[str, Any]) -> None:
    async def _body() -> None:
        services = compliance_e2e_services
        settings: StorageSettings = services["settings"]
        raw = Minio(
            services["minio_endpoint"],
            access_key=services["minio_access"],
            secret_key=services["minio_secret"],
            secure=services["minio_secure"],
        )
        await _ensure_bucket(raw, settings.MINIO_BUCKET_HARD_CASES)

        async with asyncpg.connect(services["dsn"]) as setup_conn:
            for stmt in _migration_sql_chunks():
                await setup_conn.execute(stmt)

        storage = MinioStorageClient.from_connection(
            services["minio_endpoint"],
            services["minio_access"],
            services["minio_secret"],
            keyframes_bucket=settings.MINIO_BUCKET_SOP_KEYFRAMES,
            videos_bucket=settings.MINIO_BUCKET_SOP_VIDEOS,
            hard_cases_bucket=settings.MINIO_BUCKET_HARD_CASES,
            secure=services["minio_secure"],
        )
        pg = await PostgresDataLakeSamplesClient.connect(
            services["dsn"],
            table_name=settings.POSTGRES_TABLE_DATA_LAKE_SAMPLES,
            min_size=1,
            max_size=4,
        )
        writer = AutoDivergenceLakeWriter(storage, pg, minio_uri_prefix=settings.MINIO_URI_PREFIX)
        ws = f"e2e-{uuid.uuid4().hex[:8]}"
        upload = UncertainFrameUpload(
            workstation_id=ws,
            sop_id="00000000-0000-4000-8000-000000000001",
            sop_step=1,
            captured_at=datetime(2026, 4, 14, 10, 0, 0, tzinfo=timezone.utc),
            edge_confidence=0.5,
            edge_level=ConfidenceLevel.UNCERTAIN,
            frame_jpeg=b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 64,
            fsm_state=None,
        )
        vlm = VlmComplianceVerdict(is_anomaly=True, reason="test", confidence=0.99)
        path = await writer.save_auto_divergence(
            upload=upload,
            vlm_verdict=vlm,
            reason_code="EDGE_COMPLIANT_VLM_ANOMALY",
        )
        assert path.startswith(settings.MINIO_URI_PREFIX)
        rel = path.removeprefix(settings.MINIO_URI_PREFIX)
        bucket, _, obj_key = rel.partition("/")
        assert bucket == settings.MINIO_BUCKET_HARD_CASES

        tbl = settings.POSTGRES_TABLE_DATA_LAKE_SAMPLES
        async with asyncpg.connect(services["dsn"]) as c2:
            row = await c2.fetchrow(
                f"SELECT frame_path, label, source, sop_id, reason_code FROM {tbl} WHERE workstation_id = $1",
                ws,
            )
        assert row is not None
        assert row["frame_path"] == path
        assert row["label"] == "ANOMALY"
        assert row["source"] == "auto"
        assert row["sop_id"] == upload.sop_id
        assert row["reason_code"] == "EDGE_COMPLIANT_VLM_ANOMALY"

        await asyncio.to_thread(raw.remove_object, bucket, obj_key)
        async with asyncpg.connect(services["dsn"]) as c3:
            await c3.execute(f"DELETE FROM {tbl} WHERE workstation_id = $1", ws)
        await pg.close()

    asyncio.run(_body())


@pytest.fixture(scope="module")
def compliance_pipeline_kafka() -> dict[str, Any]:
    """gRPC + Kafka 集成：需 ``COMPLIANCE_PIPELINE_E2E=1`` 与可达的 bootstrap。"""
    if not _pipeline_e2e_opt_in():
        pytest.skip(
            "设置 COMPLIANCE_PIPELINE_E2E=1 以运行 gRPC→Kafka 流水线（见 tests/integration/README.md）"
        )
    bootstrap = _kafka_bootstrap()
    if not _probe_kafka(bootstrap):
        pytest.skip(
            f"无法连接 Kafka bootstrap={bootstrap!r}；请先 docker compose -f deploy/docker-compose.integration.yml up -d"
        )
    return {"kafka_bootstrap": bootstrap}


@pytest.mark.integration
def test_grpc_uncertain_frame_triggers_kafka_compliance_event(
    compliance_pipeline_kafka: dict[str, Any],
) -> None:
    """边缘帧经 gRPC 入站 → Mock VLM 判异常 → ``compliance.events`` 出现 JSON 消息。"""

    async def _body() -> None:
        from kafka import KafkaConsumer

        bootstrap = compliance_pipeline_kafka["kafka_bootstrap"]
        topic = get_kafka_settings().TOPIC_COMPLIANCE_EVENTS
        fixed_now = datetime(2026, 4, 15, 9, 30, 0, tzinfo=timezone.utc)
        ws = f"pipe-{uuid.uuid4().hex[:10]}"

        producer = ComplianceKafkaProducer.from_bootstrap(bootstrap, topic=topic)

        class _AsyncKafkaPublisher:
            def __init__(self, kp: ComplianceKafkaProducer) -> None:
                self._kp = kp

            async def publish(self, event: ComplianceEvent) -> None:
                await asyncio.to_thread(self._send_flush, event)

            def _send_flush(self, event: ComplianceEvent) -> None:
                self._kp.send(event)
                self._kp.flush(timeout=20.0)

        class _MockVlm:
            async def analyze_uncertain_frame(
                self,
                *,
                upload: UncertainFrameUpload,
                sop_step_context: str,
            ) -> VlmComplianceVerdict:
                _ = upload, sop_step_context
                return VlmComplianceVerdict(
                    is_anomaly=True,
                    reason="integration_stub",
                    confidence=0.91,
                )

        lake = AsyncMock()
        orch = UncertainFrameSlowPathOrchestrator(
            SlowPathDependencies(
                vlm=_MockVlm(),
                lake=lake,
                events=_AsyncKafkaPublisher(producer),
            )
        )

        async def _handler(upload: UncertainFrameUpload) -> None:
            await orch.process(
                upload,
                InferenceResult(
                    level=ConfidenceLevel.UNCERTAIN,
                    confidence=float(upload.edge_confidence),
                ),
                sop_step_context="integration_ctx",
                clock=lambda: fixed_now,
            )

        server = create_uncertain_frame_upload_aio_server(_handler)
        port = int(server.add_insecure_port("127.0.0.1:0"))
        assert port > 0
        await server.start()

        consumer = KafkaConsumer(
            topic,
            bootstrap_servers=bootstrap,
            auto_offset_reset="earliest",
            group_id=f"pytest-compliance-pipeline-{uuid.uuid4().hex}",
            value_deserializer=lambda b: json.loads(b.decode("utf-8")),
        )
        consumer.poll(timeout_ms=3000)

        try:
            async with aio.insecure_channel(f"127.0.0.1:{port}") as channel:
                stub = FrameUploadServiceStub(channel)

                async def _chunks() -> AsyncIterator[frame_upload_pb2.FrameUploadChunk]:
                    md = frame_upload_pb2.UncertainFrameMetadata(
                        workstation_id=ws,
                        sop_id="00000000-0000-4000-8000-0000000000aa",
                        sop_step=2,
                        captured_at="2026-04-15T09:00:00+00:00",
                        edge_confidence=0.55,
                        edge_level=frame_upload_pb2.UNCERTAIN,
                    )
                    c0 = frame_upload_pb2.FrameUploadChunk()
                    c0.metadata.CopyFrom(md)
                    yield c0
                    c1 = frame_upload_pb2.FrameUploadChunk()
                    c1.jpeg_chunk = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 32
                    yield c1

                ack = await stub.UploadUncertainFrame(_chunks())
                assert ack.accepted is True

            got: dict[str, Any] | None = None
            deadline = time.monotonic() + 45.0
            while time.monotonic() < deadline:
                batch = consumer.poll(timeout_ms=2000)
                if not batch:
                    continue
                for _tp, records in batch.items():
                    for rec in records:
                        v = rec.value
                        if isinstance(v, dict) and v.get("workstation_id") == ws:
                            got = v
                            break
                    if got:
                        break
                if got:
                    break

            assert got is not None, "Kafka 未收到匹配 workstation_id 的 compliance 事件"
            assert got["event_type"] == "SOP_VIOLATION"
            assert got["sop_step"] == 2
            assert got["confidence"] == pytest.approx(0.91)
            assert got["frame_path"] == ""
            assert got["timestamp"] == "2026-04-15T09:30:00Z"
            lake.save_auto_divergence.assert_not_awaited()
        finally:
            consumer.close()
            await server.stop(1.0)
            producer.close()

    asyncio.run(_body())
