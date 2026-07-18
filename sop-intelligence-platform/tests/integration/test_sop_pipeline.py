"""T10 · SOP 生成全链路端到端集成测试。

验证从「专家视频进入对象存储」到「PostgreSQL 中可查询的 SOPDocument」的完整 Pipeline，
按任务依赖 T01→T10 拆成 10 个可观测阶段（与 docs/module-specs/sop-engine.md 一致）。

**运行环境**

- 本地或 `.idx/dev.nix` / IDX **Push to Cloud** 云端沙盒中需已启动 **MinIO** 与 **PostgreSQL**，
  并已执行迁移 `data/migrations/001_create_sop_versions.sql`。
- 连接参数通过环境变量覆盖（与沙盒 `env` 导出一致；未设置时使用常见 Docker 默认值）：

  - ``SOP_E2E_POSTGRES_DSN`` — 默认 ``postgresql://postgres:postgres@127.0.0.1:5432/postgres``
  - ``SOP_E2E_MINIO_ENDPOINT`` — 默认 ``127.0.0.1:9000``
  - ``SOP_E2E_MINIO_ACCESS_KEY`` / ``SOP_E2E_MINIO_SECRET_KEY`` — 默认 ``minioadmin``

**运行示例**（须显式开启，避免未起 Docker 时长时间探测网络）：

```bash
export SOP_E2E=1
pytest tests/integration/test_sop_pipeline.py -v -m e2e
```

说明：当前 ``src/api/routes/sop.py`` 与 ``version_manager`` 尚未实现，本测试在集成层直接编排
``VideoParser`` → ``VLMAnnotator`` → ``SOPCompiler`` → 存储适配器，等价于 T08 同步 Pipeline 的契约行为。
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import asyncpg
import pytest
from minio import Minio
from minio.error import S3Error

from src.adapters.storage.minio_client import MinioStorageClient
from src.adapters.storage.postgres_client import PostgresSopVersionsClient
from src.config.storage import StorageSettings
from src.services.sop_engine.sop_compiler import SOPCompiler
from src.services.sop_engine.video_parser import MockVideoParser
from src.services.sop_engine.vlm_annotator import MockVLMAnnotator
from src.types.sop import ActionSegment, SOPDocument


# ---------------------------------------------------------------------------
# 环境与服务探测
# ---------------------------------------------------------------------------


def _env_dsn() -> str:
    return os.environ.get(
        "SOP_E2E_POSTGRES_DSN",
        "postgresql://postgres:postgres@127.0.0.1:5432/postgres",
    )


def _env_minio_params() -> tuple[str, str, str, bool]:
    endpoint = os.environ.get("SOP_E2E_MINIO_ENDPOINT", "127.0.0.1:9000")
    access = os.environ.get("SOP_E2E_MINIO_ACCESS_KEY", "minioadmin")
    secret = os.environ.get("SOP_E2E_MINIO_SECRET_KEY", "minioadmin")
    secure = os.environ.get("SOP_E2E_MINIO_SECURE", "").lower() in ("1", "true", "yes")
    return endpoint, access, secret, secure


def _e2e_opt_in() -> bool:
    return os.environ.get("SOP_E2E", "").lower() in ("1", "true", "yes", "on")


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


@pytest.fixture(scope="module")
def e2e_services() -> dict[str, Any]:
    """需 ``SOP_E2E=1``；若无法连通 MinIO/PostgreSQL，跳过整个模块。"""
    if not _e2e_opt_in():
        pytest.skip("设置 SOP_E2E=1 以运行 T10 E2E（需 MinIO + PostgreSQL，见模块文档）")

    dsn = _env_dsn()
    ep, ak, sk, sec = _env_minio_params()
    ok_pg = asyncio.run(_probe_postgres(dsn))
    ok_m = _probe_minio(ep, ak, sk, sec)
    if not (ok_pg and ok_m):
        pytest.skip(
            "E2E 需要可用的 PostgreSQL 与 MinIO；请启动服务并应用迁移，或检查环境变量："
            f" SOP_E2E_POSTGRES_DSN={dsn!r} SOP_E2E_MINIO_ENDPOINT={ep!r}"
        )

    settings = StorageSettings()
    return {
        "dsn": dsn,
        "minio_endpoint": ep,
        "minio_access": ak,
        "minio_secret": sk,
        "minio_secure": sec,
        "settings": settings,
    }


async def _ensure_bucket(client: Minio, name: str) -> None:
    def _ensure() -> None:
        if not client.bucket_exists(name):
            client.make_bucket(name)

    await asyncio.to_thread(_ensure)


def _parse_storage_path(path: str) -> tuple[str, str]:
    """``bucket/key`` → (bucket, key)。"""
    if "/" not in path:
        raise ValueError(f"unexpected path: {path!r}")
    bucket, _, key = path.partition("/")
    return bucket, key


@asynccontextmanager
async def _e2e_clients(
    services: dict[str, Any],
) -> AsyncIterator[tuple[MinioStorageClient, PostgresSopVersionsClient, Minio]]:
    settings: StorageSettings = services["settings"]
    raw = Minio(
        services["minio_endpoint"],
        access_key=services["minio_access"],
        secret_key=services["minio_secret"],
        secure=services["minio_secure"],
    )
    await _ensure_bucket(raw, settings.MINIO_BUCKET_SOP_KEYFRAMES)
    await _ensure_bucket(raw, settings.MINIO_BUCKET_SOP_VIDEOS)

    storage = MinioStorageClient.from_connection(
        services["minio_endpoint"],
        services["minio_access"],
        services["minio_secret"],
        keyframes_bucket=settings.MINIO_BUCKET_SOP_KEYFRAMES,
        videos_bucket=settings.MINIO_BUCKET_SOP_VIDEOS,
        secure=services["minio_secure"],
    )
    pg = await PostgresSopVersionsClient.connect(
        services["dsn"],
        table_name=settings.POSTGRES_TABLE_SOP_VERSIONS,
        min_size=1,
        max_size=4,
    )
    try:
        yield storage, pg, raw
    finally:
        await pg.close()


async def _cleanup_artifacts(
    raw: Minio,
    settings: StorageSettings,
    *,
    sop_id: str,
    product_id: str,
    video_filename: str,
) -> None:
    """测试结束后删除 MinIO 对象与 PostgreSQL 行。"""

    async def _del_obj(bucket: str, key: str) -> None:
        try:
            await asyncio.to_thread(raw.remove_object, bucket, key)
        except S3Error:
            pass

    await _del_obj(
        settings.MINIO_BUCKET_SOP_VIDEOS,
        f"{product_id}/{video_filename}",
    )
    for step_id in range(1, 32):
        await _del_obj(
            settings.MINIO_BUCKET_SOP_KEYFRAMES,
            f"{sop_id}/step_{step_id}.jpg",
        )

    async with asyncpg.connect(_env_dsn(), timeout=5.0) as conn:
        await conn.execute(
            f'DELETE FROM "{settings.POSTGRES_TABLE_SOP_VERSIONS}" WHERE sop_id = $1::uuid',
            sop_id,
        )


async def _run_ten_step_pipeline(
    *,
    services: dict[str, Any],
    annotator: MockVLMAnnotator,
    video_bytes: bytes,
) -> SOPDocument:
    """执行 10 步 Pipeline，返回已持久化且 keyframe_path 已对齐 MinIO 的文档。"""
    settings: StorageSettings = services["settings"]
    run_product = f"E2E-{uuid.uuid4().hex[:8]}"
    video_filename = "expert_clip.bin"
    video_minio_path: str | None = None
    sop_id_final: str | None = None

    async with _e2e_clients(services) as (storage, pg, raw):
        try:
            # --- Step 1 (T01)：核心类型与模型可用（导入即代表 Schema 契约就绪） ---
            _ = (ActionSegment, SOPDocument)

            # --- Step 2 (T02)：加载存储与桶配置 ---
            assert settings.MINIO_BUCKET_SOP_KEYFRAMES
            assert settings.MINIO_BUCKET_SOP_VIDEOS
            assert settings.POSTGRES_TABLE_SOP_VERSIONS

            # --- Step 3：「视频上传」— 原始文件写入 sop-videos ---
            video_minio_path = await storage.upload_video(
                run_product, video_filename, video_bytes
            )
            assert run_product in video_minio_path
            assert video_filename in video_minio_path

            # --- Step 4 (T03)：VideoParser 分段 ---
            parser = MockVideoParser()
            segments = parser.parse(video_minio_path)
            assert len(segments) >= 3
            times = [s.start_time_sec for s in segments]
            assert times == sorted(times)

            # --- Step 5：按 segment 抽取关键帧 JPEG ---
            keyframes: dict[int, bytes] = {}
            for seg in segments:
                keyframes[seg.segment_id] = parser.extract_keyframe(
                    video_minio_path, seg.keyframe_index
                )
                assert keyframes[seg.segment_id][:3] == b"\xff\xd8\xff"

            # --- Step 6 (T04)：VLM 语义标注（Mock / 或真实 vLLM 替换实现） ---
            annotated = await annotator.annotate(
                segments, keyframes, product_context=run_product
            )
            assert len(annotated) == len(segments)

            # --- Step 7 (T05)：SOPCompiler 组装（先用占位路径满足校验） ---
            placeholder_paths = {
                seg.segment_id: f"{settings.MINIO_BUCKET_SOP_KEYFRAMES}/__pending__/step_{seg.segment_id}.jpg"
                for seg in segments
            }
            compiler = SOPCompiler()
            doc = compiler.compile(
                product_id=run_product,
                annotated_steps=annotated,
                segments=segments,
                keyframe_paths=placeholder_paths,
                source_video_paths=[video_minio_path],
                version="v1.0",
            )
            assert doc.total_steps >= 3
            assert doc.steps[0].step_id == 1

            # --- Step 8 (T06a)：关键帧实际上传 MinIO，并写回真实路径 ---
            sorted_segs = sorted(segments, key=lambda s: s.segment_id)
            new_steps = []
            for st in doc.steps:
                seg = sorted_segs[st.step_id - 1]
                jpeg = keyframes[seg.segment_id]
                path = await storage.upload_keyframe(doc.sop_id, st.step_id, jpeg)
                assert path.startswith(f"{settings.MINIO_BUCKET_SOP_KEYFRAMES}/")
                new_steps.append(st.model_copy(update={"keyframe_path": path}))
            doc = doc.model_copy(update={"steps": new_steps, "total_steps": len(new_steps)})

            # --- Step 9 (T06b/T07)：版本快照写入 PostgreSQL ---
            saved_id = await pg.save_sop_version(doc)
            assert saved_id == doc.sop_id
            sop_id_final = doc.sop_id

            # --- Step 10 (T08 等价)：读取结构化数据并校验对象存储可访问 ---
            loaded = await pg.get_sop_by_id(doc.sop_id)
            assert loaded is not None
            assert loaded.total_steps == doc.total_steps
            assert loaded.steps[0].keyframe_path.startswith(
                f"{settings.MINIO_BUCKET_SOP_KEYFRAMES}/"
            )

            kb, kk = _parse_storage_path(loaded.steps[0].keyframe_path)
            await asyncio.to_thread(raw.stat_object, kb, kk)

            return loaded
        finally:
            if video_minio_path and sop_id_final:
                await _cleanup_artifacts(
                    raw,
                    settings,
                    sop_id=sop_id_final,
                    product_id=run_product,
                    video_filename=video_filename,
                )


@pytest.mark.e2e
def test_full_pipeline_e2e_ten_steps(e2e_services: dict[str, Any]) -> None:
    """全链路：上传 → 解析 → 抽帧 → 标注 → 编译 → 写 MinIO/Postgres → 读回校验。"""

    annotator = MockVLMAnnotator()
    video_payload = b"FAKE_MP4_CONTENT_FOR_MINIO_E2E\n" * 8

    doc = asyncio.run(
        _run_ten_step_pipeline(
            services=e2e_services,
            annotator=annotator,
            video_bytes=video_payload,
        )
    )

    assert doc.status == "draft"
    assert doc.total_steps >= 3
    for st in doc.steps:
        assert st.description
        assert st.action_object
        assert st.warnings is not None


@pytest.mark.e2e
def test_pipeline_vlm_degraded_output_does_not_abort(e2e_services: dict[str, Any]) -> None:
    """VLM 返回非法内容时降级为「[待人工补充]」，Pipeline 仍落库成功。"""

    annotator = MockVLMAnnotator()
    annotator.inject_responses(
        {
            1: '{"step_description": "正常一步", "action_object": "零件A", "warnings": []}',
            2: "not-json-at-all {{{",
            3: "",
        }
    )
    video_payload = b"FAKE_MP4_VLM_FAIL\n" * 4

    doc = asyncio.run(
        _run_ten_step_pipeline(
            services=e2e_services,
            annotator=annotator,
            video_bytes=video_payload,
        )
    )

    degraded = [s for s in doc.steps if "[待人工补充]" in s.description]
    assert len(degraded) >= 1
