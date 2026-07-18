"""分歧帧 / 难例：MinIO 存图 + PostgreSQL 元数据（供合规编排注入）。

``src/services/compliance/AGENTS.md``：对象写入后必须有 PG 记录；本模块在 PG
失败时尝试删除已上传的 MinIO 对象并抛出明确异常，不吞错。
"""

from __future__ import annotations

import uuid

from src.adapters.storage.minio_client import MinioStorageClient
from src.adapters.storage.postgres_client import PostgresDataLakeSamplesClient
from src.config.storage import get_storage_settings
from src.types.frames import UncertainFrameUpload
from src.types.models import VlmComplianceVerdict


class DataLakeWriteError(RuntimeError):
    """MinIO 与 PG 配对写入任一步失败，或补偿删除失败。"""


def _vlm_pseudo_label(vlm: VlmComplianceVerdict) -> str:
    """VLM 结论作伪标签（与 ``compliance/AGENTS.md`` 一致）。"""
    return "ANOMALY" if vlm.is_anomaly else "COMPLIANT"


class AutoDivergenceLakeWriter:
    """实现 ``DataLakeWriterPort.save_auto_divergence`` 的具体 I/O。"""

    def __init__(
        self,
        minio: MinioStorageClient,
        pg: PostgresDataLakeSamplesClient,
        *,
        minio_uri_prefix: str | None = None,
    ) -> None:
        self._minio = minio
        self._pg = pg
        prefix = minio_uri_prefix if minio_uri_prefix is not None else get_storage_settings().MINIO_URI_PREFIX
        self._uri_prefix = prefix if prefix.endswith("://") else f"{prefix}://"

    async def save_auto_divergence(
        self,
        *,
        upload: UncertainFrameUpload,
        vlm_verdict: VlmComplianceVerdict,
        reason_code: str,
    ) -> str:
        """先写 MinIO，再写 PG；PG 失败则补偿删除对象并抛 ``DataLakeWriteError``。"""
        sample_id = uuid.uuid4()
        try:
            storage_path = await self._minio.upload_hard_case_jpeg(
                workstation_id=upload.workstation_id,
                captured_at=upload.captured_at,
                image_bytes=upload.frame_jpeg,
                object_uuid=str(sample_id),
            )
        except Exception as exc:
            raise DataLakeWriteError("MinIO 上传分歧帧失败") from exc

        frame_path = f"{self._uri_prefix}{storage_path}"
        rc = reason_code if reason_code else None
        try:
            await self._pg.insert_auto_sample(
                sample_id=sample_id,
                frame_path=frame_path,
                label=_vlm_pseudo_label(vlm_verdict),
                sop_step=upload.sop_step,
                workstation_id=upload.workstation_id,
                source="auto",
                recorded_at=upload.captured_at,
                sop_id=upload.sop_id,
                reason_code=rc,
            )
        except Exception as pg_exc:
            try:
                await self._minio.remove_object_at_storage_path(storage_path)
            except Exception as cleanup_exc:
                raise DataLakeWriteError(
                    f"PostgreSQL 写入 data_lake_samples 失败，且补偿删除 MinIO 对象失败；"
                    f"孤立对象 storage_path={storage_path!r}；cleanup={cleanup_exc!r}"
                ) from pg_exc
            raise DataLakeWriteError(
                "PostgreSQL 写入 data_lake_samples 失败，已删除对应 MinIO 对象（补偿成功）"
            ) from pg_exc

        return frame_path


__all__ = [
    "AutoDivergenceLakeWriter",
    "DataLakeWriteError",
]
