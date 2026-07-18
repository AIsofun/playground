"""关键帧上传（MinIO）与 SOP 快照读写（PostgreSQL，经适配器）。"""

from __future__ import annotations

import asyncio
import re
import uuid
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from src.services.sop_engine.sop_compiler import _normalize_annotated_step
from src.types.sop import ActionSegment, AnnotatedStep, SOPDocument, SOPStep

if TYPE_CHECKING:
    from src.adapters.storage.minio_client import MinioStorageClient
    from src.adapters.storage.postgres_client import PostgresSopVersionsClient

__all__ = ["VersionManager", "VersionManagerError"]


class VersionManagerError(Exception):
    """版本管理业务错误（如基线文档不存在、版本号无法解析）。"""


def _minio_url_from_object_path(object_path: str) -> str:
    """将 ``bucket/key`` 转为与 Schema 一致的 ``minio://bucket/key``。"""
    p = object_path.strip()
    if p.startswith("minio://"):
        return p
    return f"minio://{p}"


def _bump_minor_version(full_version: str, product_id: str) -> str:
    """
    将 ``{product_id}-v{major}.{minor}`` 的 minor 加 1。
    """
    esc = re.escape(product_id)
    m = re.match(rf"^{esc}-v(\d+)\.(\d+)$", full_version)
    if not m:
        raise VersionManagerError(
            f"无法解析版本号以递增 minor：{full_version!r}（期望前缀 {product_id!r}-vMAJOR.MINOR）"
        )
    major, minor = int(m.group(1)), int(m.group(2))
    return f"{product_id}-v{major}.{minor + 1}"


def _action_type_queues(steps: list[SOPStep]) -> dict[str, deque[int]]:
    q: dict[str, deque[int]] = defaultdict(deque)
    for i, st in enumerate(steps):
        q[st.action_type].append(i)
    return q


class VersionManager:
    """上传关键帧、写入快照，并在换型场景下做按动作类型的增量合并。"""

    def __init__(
        self,
        *,
        minio: MinioStorageClient,
        postgres: PostgresSopVersionsClient,
    ) -> None:
        self._minio = minio
        self._pg = postgres

    @property
    def sop_versions_postgres(self) -> "PostgresSopVersionsClient":
        """暴露 SOP 快照客户端，供 FSM 编译等流程复用同一连接池。"""
        return self._pg

    async def save(
        self,
        doc: SOPDocument,
        *,
        keyframe_bytes: dict[int, bytes],
    ) -> SOPDocument:
        """
        1. 并发上传各 ``step_id`` 对应的关键帧
        2. 将 ``keyframe_path`` 更新为 MinIO 对象 URL
        3. 将完整 ``SOPDocument`` 写入 ``sop_versions``
        """
        for st in doc.steps:
            if st.step_id not in keyframe_bytes:
                missing = [s.step_id for s in doc.steps if s.step_id not in keyframe_bytes]
                raise VersionManagerError(f"缺少关键帧字节，step_ids={missing}")

        async def _upload_one(st: SOPStep) -> tuple[int, str]:
            raw = await self._minio.upload_keyframe(
                doc.sop_id,
                st.step_id,
                keyframe_bytes[st.step_id],
            )
            return st.step_id, _minio_url_from_object_path(raw)

        results = await asyncio.gather(*(_upload_one(st) for st in doc.steps))
        path_by_step = dict(results)

        new_steps: list[SOPStep] = []
        for st in doc.steps:
            new_steps.append(
                st.model_copy(update={"keyframe_path": path_by_step[st.step_id]})
            )

        updated = doc.model_copy(
            update={
                "steps": new_steps,
                "total_steps": len(new_steps),
            }
        )
        await self._pg.save_sop_version(updated)
        return updated

    async def get(self, sop_id: str) -> SOPDocument | None:
        """从 PostgreSQL 读取 ``sop_versions`` 快照。"""
        return await self._pg.get_sop_by_id(sop_id)

    async def diff_update(
        self,
        base_sop_id: str,
        new_segments: list[ActionSegment],
        new_annotations: list[AnnotatedStep],
        *,
        keyframe_bytes_by_segment_id: dict[int, bytes],
    ) -> SOPDocument:
        """
        换型：按 ``action_type``（``ActionSegment.action_class``）与基线步骤对齐，
        仅替换匹配到的步骤；版本号 minor +1；未匹配步骤保持原 ``keyframe_path``。
        """
        base = await self._pg.get_sop_by_id(base_sop_id)
        if base is None:
            raise VersionManagerError(f"基线 SOP 不存在：sop_id={base_sop_id!r}")

        seg_by_id = {s.segment_id: s for s in new_segments}
        sorted_ann = sorted(new_annotations, key=lambda a: a.segment_id)

        for ann in sorted_ann:
            if ann.segment_id not in seg_by_id:
                raise VersionManagerError(
                    f"segment_id={ann.segment_id} 在 new_segments 中不存在",
                )
            if ann.segment_id not in keyframe_bytes_by_segment_id:
                raise VersionManagerError(
                    f"缺少 segment_id={ann.segment_id} 的关键帧字节",
                )

        queues = _action_type_queues(base.steps)
        new_sop_id = str(uuid.uuid4())
        new_version = _bump_minor_version(base.version, base.product_id)

        merged_steps: list[SOPStep] = [s.model_copy() for s in base.steps]

        for ann in sorted_ann:
            seg = seg_by_id[ann.segment_id]
            q = queues.get(seg.action_class)
            if not q:
                raise VersionManagerError(
                    f"基线文档中不存在 action_type={seg.action_class!r}，无法合并换型片段",
                )
            idx = q.popleft()
            norm = _normalize_annotated_step(ann)
            raw_path = await self._minio.upload_keyframe(
                new_sop_id,
                merged_steps[idx].step_id,
                keyframe_bytes_by_segment_id[seg.segment_id],
            )
            keyframe_path = _minio_url_from_object_path(raw_path)
            merged_steps[idx] = SOPStep(
                step_id=merged_steps[idx].step_id,
                description=norm.step_description,
                action_object=norm.action_object,
                keyframe_path=keyframe_path,
                video_timestamp=seg.start_time_sec,
                action_type=seg.action_class,
                warnings=norm.warnings,
            )

        new_doc = SOPDocument(
            sop_id=new_sop_id,
            product_id=base.product_id,
            version=new_version,
            steps=merged_steps,
            total_steps=len(merged_steps),
            created_at=datetime.now(timezone.utc),
            source_video_paths=list(base.source_video_paths),
            status=base.status,
        )
        validated = SOPDocument.model_validate(new_doc.model_dump(mode="json"))
        await self._pg.save_sop_version(validated)
        return validated

    async def publish(self, sop_id: str) -> SOPDocument:
        """将 status 从 draft 更新为 published（依赖 DB UPDATE，后续任务实现）。"""
        raise NotImplementedError(
            f"publish(sop_id={sop_id!r}) 尚未实现：需要 PostgreSQL 更新语句与弃用旧版策略"
        )
