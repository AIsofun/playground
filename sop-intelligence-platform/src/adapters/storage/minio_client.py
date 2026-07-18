"""MinIO（S3 兼容）对象存储 I/O 封装。

仅负责 put_object 等底层读写，不包含 SOP 业务分支逻辑。
"""

from __future__ import annotations

import asyncio
import io
import uuid
from datetime import datetime

from minio import Minio


class MinioStorageClient:
    """按约定路径上传关键帧与原始视频，返回 `bucket/object_key` 形式路径。"""

    def __init__(
        self,
        client: Minio,
        keyframes_bucket: str,
        videos_bucket: str,
        hard_cases_bucket: str | None = None,
    ) -> None:
        self._client = client
        self._keyframes_bucket = keyframes_bucket
        self._videos_bucket = videos_bucket
        self._hard_cases_bucket = hard_cases_bucket

    @classmethod
    def from_connection(
        cls,
        endpoint: str,
        access_key: str,
        secret_key: str,
        *,
        keyframes_bucket: str,
        videos_bucket: str,
        hard_cases_bucket: str | None = None,
        secure: bool = False,
    ) -> MinioStorageClient:
        """使用显式连接参数构造客户端（endpoint 形如 ``host:9000``）。"""
        if hard_cases_bucket is None:
            from src.config.storage import get_storage_settings

            hard_cases_bucket = get_storage_settings().MINIO_BUCKET_HARD_CASES
        client = Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
        )
        return cls(client, keyframes_bucket, videos_bucket, hard_cases_bucket)

    async def upload_keyframe(self, sop_id: str, step_id: int, image_bytes: bytes) -> str:
        """上传关键帧，返回路径：``{keyframes_bucket}/{sop_id}/step_{step_id}.jpg``。"""
        object_name = f"{sop_id}/step_{step_id}.jpg"
        data = io.BytesIO(image_bytes)
        length = len(image_bytes)
        await asyncio.to_thread(
            self._client.put_object,
            self._keyframes_bucket,
            object_name,
            data,
            length,
            content_type="image/jpeg",
        )
        return f"{self._keyframes_bucket}/{object_name}"

    async def upload_video(self, product_id: str, filename: str, video_bytes: bytes) -> str:
        """上传原始视频，返回路径：``{videos_bucket}/{product_id}/{filename}``。"""
        object_name = f"{product_id}/{filename}"
        data = io.BytesIO(video_bytes)
        length = len(video_bytes)
        await asyncio.to_thread(
            self._client.put_object,
            self._videos_bucket,
            object_name,
            data,
            length,
            content_type="application/octet-stream",
        )
        return f"{self._videos_bucket}/{object_name}"

    async def upload_hard_case_jpeg(
        self,
        *,
        workstation_id: str,
        captured_at: datetime,
        image_bytes: bytes,
        object_uuid: str | None = None,
    ) -> str:
        """上传分歧/难例 JPEG，返回 ``{hard_cases_bucket}/{object_key}``（无 ``minio://`` 前缀）。

        路径约定：``{bucket}/{workstation_id}/{yyyy}/{mm}/{dd}/{uuid}.jpg``。
        """
        if self._hard_cases_bucket is None:
            raise ValueError("MinioStorageClient 未配置 hard_cases_bucket，无法上传难例帧")
        safe_ws = workstation_id.replace("/", "_").strip() or "unknown_ws"
        uid = object_uuid or str(uuid.uuid4())
        y, m, d = captured_at.year, captured_at.month, captured_at.day
        object_name = f"{safe_ws}/{y}/{m:02d}/{d:02d}/{uid}.jpg"
        data = io.BytesIO(image_bytes)
        length = len(image_bytes)
        await asyncio.to_thread(
            self._client.put_object,
            self._hard_cases_bucket,
            object_name,
            data,
            length,
            content_type="image/jpeg",
        )
        return f"{self._hard_cases_bucket}/{object_name}"

    async def remove_object_at_storage_path(self, storage_path: str) -> None:
        """删除 ``bucket/object_key`` 形式路径指向的对象（用于 PG 失败后的补偿）。"""
        if "/" not in storage_path:
            raise ValueError(f"无效的 storage_path，期望 bucket/key：{storage_path!r}")
        bucket, _, object_name = storage_path.partition("/")
        if not bucket or not object_name:
            raise ValueError(f"无效的 storage_path：{storage_path!r}")
        await asyncio.to_thread(self._client.remove_object, bucket, object_name)
